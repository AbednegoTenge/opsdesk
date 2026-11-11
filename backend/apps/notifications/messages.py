"""Who hears about an incident event, and what they are told."""

from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q

from apps.incidents.models import EventType, Incident, IncidentEvent
from apps.users.models import Role, User

from .models import Kind


@dataclass(frozen=True)
class Message:
    kind: str
    subject: str
    body: str


def _link(incident: Incident) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/incidents/{incident.pk}"


def _summary(incident: Incident) -> str:
    return (
        f"{incident.reference}: {incident.title}\n"
        f"Priority: {incident.get_priority_display()}  Status: {incident.get_status_display()}\n"
        f"{_link(incident)}"
    )


def recipients_for(event: IncidentEvent) -> list[User]:
    """People to notify about an event. The person who made the change is never notified."""
    incident = event.incident
    users: list[User] = []

    if event.event_type == EventType.CREATED:
        # The assignee, if any, hears about it through the separate ASSIGNED event.
        users = list(User.objects.filter(role=Role.ADMIN, is_active=True))
    elif event.event_type == EventType.ASSIGNED:
        to = (event.data or {}).get("to") or {}
        users = list(User.objects.filter(pk=to.get("id"), is_active=True))
    elif event.event_type == EventType.PRIORITY_CHANGED:
        ids = {incident.assignee_id, incident.reporter_id} - {None}
        users = list(User.objects.filter(pk__in=ids, is_active=True))
    elif event.event_type == EventType.SLA_BREACHED:
        # The assignee and every Admin: a breach needs someone with authority to act.
        users = list(
            User.objects.filter(is_active=True).filter(
                Q(role=Role.ADMIN) | Q(pk=incident.assignee_id)
            )
        )
    elif event.event_type == EventType.REMINDER_SENT:
        # The assignee; if nobody owns it yet, the Admins, so it gets picked up.
        if incident.assignee_id:
            users = list(User.objects.filter(pk=incident.assignee_id, is_active=True))
        else:
            users = list(User.objects.filter(role=Role.ADMIN, is_active=True))

    return [u for u in users if u.pk != event.actor_id]


def message_for(event: IncidentEvent) -> Message | None:
    incident = event.incident
    actor = event.actor.full_name or event.actor.email if event.actor else "OpsDesk"

    if event.event_type == EventType.CREATED:
        return Message(
            Kind.INCIDENT_CREATED,
            f"[OpsDesk] New {incident.get_priority_display()} incident {incident.reference}",
            f"{actor} opened a new incident.\n\n{_summary(incident)}",
        )
    if event.event_type == EventType.ASSIGNED:
        return Message(
            Kind.INCIDENT_ASSIGNED,
            f"[OpsDesk] {incident.reference} assigned to you: {incident.title}",
            f"{actor} assigned this incident to you.\n\n{_summary(incident)}",
        )
    if event.event_type == EventType.PRIORITY_CHANGED:
        old, new = event.data.get("from"), event.data.get("to")
        return Message(
            Kind.PRIORITY_CHANGED,
            f"[OpsDesk] {incident.reference} priority changed to {new}",
            f"{actor} changed the priority from {old} to {new}.\n\n{_summary(incident)}",
        )
    if event.event_type == EventType.SLA_BREACHED:
        target = event.data.get("target", "resolution")
        return Message(
            Kind.SLA_BREACHED,
            f"[OpsDesk] SLA breached: {incident.reference} missed its {target} target",
            f"{incident.reference} passed its {target} deadline ({event.data.get('due_at')}).\n\n"
            f"{_summary(incident)}",
        )
    if event.event_type == EventType.REMINDER_SENT:
        owner = "You are assigned." if incident.assignee_id else "It has no assignee."
        return Message(
            Kind.REMINDER,
            f"[OpsDesk] Reminder: {incident.reference} is still {incident.get_status_display()}",
            f"This {incident.get_priority_display()} incident is unresolved. {owner}\n\n"
            f"{_summary(incident)}",
        )
    return None


NOTIFYING_EVENTS = (
    EventType.CREATED,
    EventType.ASSIGNED,
    EventType.PRIORITY_CHANGED,
    EventType.SLA_BREACHED,
    EventType.REMINDER_SENT,
)
