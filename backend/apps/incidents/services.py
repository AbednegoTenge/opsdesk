"""Incident business rules.

Every function here that changes an incident:
* runs in one database transaction,
* locks the incident row (SELECT ... FOR UPDATE) so concurrent changes serialize,
* writes the matching IncidentEvent rows in that same transaction.

Views and (later) Celery tasks call these functions; they never write incidents directly.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.users.models import Role, User
from opsdesk_tasks import outbox

from .models import (
    Comment,
    EventType,
    Incident,
    IncidentEvent,
    Priority,
    SLAPolicy,
    Status,
)

logger = logging.getLogger(__name__)


class IncidentRuleError(Exception):
    """A business rule was violated. `field` names the offending input, if any."""

    def __init__(self, message: str, field: str | None = None, code: str = "invalid"):
        super().__init__(message)
        self.message, self.field, self.code = message, field, code


# Allowed status moves. Closed -> In Progress (reopen) is Admin-only; see transition().
TRANSITIONS: dict[str, set[str]] = {
    Status.OPEN: {Status.IN_PROGRESS, Status.RESOLVED},
    Status.IN_PROGRESS: {Status.RESOLVED},
    Status.RESOLVED: {Status.CLOSED, Status.IN_PROGRESS},
    Status.CLOSED: {Status.IN_PROGRESS},
}

EDITABLE_FIELDS = ("title", "description", "priority")


@dataclass(frozen=True)
class DueTimes:
    response_due_at: object
    resolve_due_at: object


def compute_due_times(priority: str, opened_at) -> DueTimes:
    policy = SLAPolicy.objects.filter(priority=priority).first()
    if policy is None:  # no policy configured for this priority: no targets
        return DueTimes(None, None)
    return DueTimes(
        opened_at + timedelta(minutes=policy.response_minutes),
        opened_at + timedelta(minutes=policy.resolution_minutes),
    )


# Events that people are notified about. The task is published only after commit.
NOTIFY_ON = {
    EventType.CREATED,
    EventType.ASSIGNED,
    EventType.PRIORITY_CHANGED,
    EventType.SLA_BREACHED,
    EventType.REMINDER_SENT,
}


def _event(incident: Incident, actor: User | None, event_type: str, **data) -> IncidentEvent:
    event = IncidentEvent.objects.create(
        incident=incident, actor=actor, event_type=event_type, data=data
    )
    if event_type in NOTIFY_ON:
        outbox.enqueue("notifications.notify_incident_event", event_id=event.pk)
    return event


def record_system_event(incident: Incident, event_type: str, **data) -> IncidentEvent:
    """History entry written by a background job (no human actor). Call inside a transaction."""
    return _event(incident, None, event_type, **data)


def _lock(incident_id: int) -> Incident:
    return Incident.objects.select_for_update().get(pk=incident_id)


def _check_assignable(user: User | None) -> None:
    if user is None:
        return
    if not user.is_active or user.role not in (Role.ENGINEER, Role.ADMIN):
        raise IncidentRuleError(
            "Incidents can only be assigned to active Engineers or Admins.", field="assignee_id"
        )


def _user_ref(user: User | None) -> dict | None:
    return None if user is None else {"id": user.pk, "email": user.email}


# --- create / edit ----------------------------------------------------------
@transaction.atomic
def create_incident(
    *,
    actor: User,
    title: str,
    description: str = "",
    priority: str = Priority.MEDIUM,
    assignee: User | None = None,
) -> Incident:
    _check_assignable(assignee)
    incident = Incident.objects.create(
        title=title, description=description, priority=priority, reporter=actor, assignee=assignee
    )
    # Targets are measured from the stored creation time; the reference comes from the pk.
    due = compute_due_times(priority, incident.created_at)
    incident.response_due_at, incident.resolve_due_at = due.response_due_at, due.resolve_due_at
    incident.reference = f"INC-{incident.pk:06d}"
    incident.save(update_fields=["reference", "response_due_at", "resolve_due_at"])

    _event(incident, actor, EventType.CREATED, priority=priority, title=title)
    if assignee is not None:
        _event(incident, actor, EventType.ASSIGNED, **{"from": None, "to": _user_ref(assignee)})
    logger.info(
        "incident created",
        extra={"incident_id": incident.pk, "priority": priority, "actor_id": actor.pk},
    )
    return incident


@transaction.atomic
def update_incident(*, incident_id: int, actor: User, **changes) -> Incident:
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise IncidentRuleError(f"Cannot edit: {', '.join(sorted(unknown))}.")

    incident = _lock(incident_id)
    if incident.status == Status.CLOSED:
        raise IncidentRuleError(
            "Closed incidents cannot be edited. Reopen it first.", code="closed"
        )

    diffs = {
        field: {"from": getattr(incident, field), "to": value}
        for field, value in changes.items()
        if getattr(incident, field) != value
    }
    if not diffs:
        return incident

    for field, change in diffs.items():
        setattr(incident, field, change["to"])

    update_fields = [*diffs, "updated_at"]
    if "priority" in diffs:
        # Targets follow the new priority, still measured from when the incident opened.
        due = compute_due_times(incident.priority, incident.created_at)
        incident.response_due_at, incident.resolve_due_at = due.response_due_at, due.resolve_due_at
        update_fields += ["response_due_at", "resolve_due_at"]
        _event(incident, actor, EventType.PRIORITY_CHANGED, **diffs["priority"])

    incident.save(update_fields=update_fields)

    other = {k: v for k, v in diffs.items() if k != "priority"}
    if other:
        # Descriptions can be long: record that it changed, not the full text.
        if "description" in other:
            other["description"] = {"changed": True}
        _event(incident, actor, EventType.UPDATED, fields=other)
    return incident


# --- assignment -------------------------------------------------------------
@transaction.atomic
def assign_incident(*, incident_id: int, actor: User, assignee: User | None) -> Incident:
    incident = _lock(incident_id)
    if incident.status == Status.CLOSED:
        raise IncidentRuleError("Closed incidents cannot be reassigned.", code="closed")
    _check_assignable(assignee)

    previous = incident.assignee
    if (previous and previous.pk) == (assignee and assignee.pk):
        return incident  # no change, no event

    incident.assignee = assignee
    incident.save(update_fields=["assignee", "updated_at"])
    event_type = EventType.ASSIGNED if assignee else EventType.UNASSIGNED
    _event(incident, actor, event_type, **{"from": _user_ref(previous), "to": _user_ref(assignee)})
    return incident


# --- status -----------------------------------------------------------------
@transaction.atomic
def transition_incident(
    *, incident_id: int, actor: User, to_status: str, note: str = ""
) -> Incident:
    incident = _lock(incident_id)
    from_status = incident.status

    if to_status == from_status:
        raise IncidentRuleError(f"Incident is already {incident.get_status_display()}.", "status")
    if to_status not in TRANSITIONS.get(from_status, set()):
        raise IncidentRuleError(
            f"Cannot move from {Status(from_status).label} to {Status(to_status).label}.",
            field="status",
            code="invalid_transition",
        )
    if from_status == Status.CLOSED and actor.role != Role.ADMIN:
        raise IncidentRuleError(
            "Only Admins can reopen closed incidents.", field="status", code="forbidden_transition"
        )

    now = timezone.now()
    fields = ["status", "updated_at"]

    if to_status == Status.IN_PROGRESS:
        if incident.assignee_id is None:
            # Starting work on an unassigned incident takes it.
            incident.assignee = actor
            fields.append("assignee")
            _event(incident, actor, EventType.ASSIGNED, **{"from": None, "to": _user_ref(actor)})
        if incident.acknowledged_at is None:
            incident.acknowledged_at = now
            fields.append("acknowledged_at")
        if from_status in (Status.RESOLVED, Status.CLOSED):  # reopen
            incident.resolved_at = None
            incident.closed_at = None
            fields += ["resolved_at", "closed_at"]
    elif to_status == Status.RESOLVED:
        incident.resolved_at = now
        fields.append("resolved_at")
        if incident.acknowledged_at is None:  # resolved straight from Open
            incident.acknowledged_at = now
            fields.append("acknowledged_at")
    elif to_status == Status.CLOSED:
        incident.closed_at = now
        fields.append("closed_at")

    incident.status = to_status
    incident.save(update_fields=fields)
    _event(
        incident,
        actor,
        EventType.STATUS_CHANGED,
        **{"from": from_status, "to": to_status, "note": note},
    )
    if note:
        Comment.objects.create(incident=incident, author=actor, body=note)
    return incident


# --- comments ---------------------------------------------------------------
@transaction.atomic
def add_comment(*, incident_id: int, actor: User, body: str) -> Comment:
    incident = _lock(incident_id)
    comment = Comment.objects.create(incident=incident, author=actor, body=body)
    Incident.objects.filter(pk=incident.pk).update(updated_at=timezone.now())
    _event(incident, actor, EventType.COMMENT_ADDED, comment_id=comment.pk)
    return comment


def _check_comment_owner(comment: Comment, actor: User) -> None:
    if comment.author_id != actor.pk and actor.role != Role.ADMIN:
        raise IncidentRuleError(
            "Only the author or an Admin can change this comment.", code="forbidden"
        )


@transaction.atomic
def edit_comment(*, comment_id: int, actor: User, body: str) -> Comment:
    comment = Comment.objects.select_for_update().get(pk=comment_id)
    _check_comment_owner(comment, actor)
    if comment.body == body:
        return comment
    comment.body = body
    comment.edited_at = timezone.now()
    comment.save(update_fields=["body", "edited_at"])
    _event(comment.incident, actor, EventType.COMMENT_EDITED, comment_id=comment.pk)
    return comment


@transaction.atomic
def delete_comment(*, comment_id: int, actor: User) -> None:
    comment = Comment.objects.select_for_update().get(pk=comment_id)
    _check_comment_owner(comment, actor)
    incident = comment.incident
    pk = comment.pk
    comment.delete()
    _event(incident, actor, EventType.COMMENT_DELETED, comment_id=pk)


# --- delete -----------------------------------------------------------------
@transaction.atomic
def delete_incident(*, incident_id: int, actor: User) -> None:
    incident = _lock(incident_id)
    logger.warning(
        "incident deleted",
        extra={"incident_id": incident.pk, "reference": incident.reference, "actor_id": actor.pk},
    )
    incident.delete()
