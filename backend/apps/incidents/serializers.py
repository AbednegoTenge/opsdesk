from rest_framework import serializers

from apps.users.models import User

from .models import Comment, Incident, IncidentEvent, Priority, SLAPolicy, Status


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role"]


class IncidentListSerializer(serializers.ModelSerializer):
    reporter = UserSummarySerializer(read_only=True)
    assignee = UserSummarySerializer(read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id",
            "reference",
            "title",
            "priority",
            "status",
            "sla_status",
            "reporter",
            "assignee",
            "response_due_at",
            "resolve_due_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class IncidentDetailSerializer(IncidentListSerializer):
    class Meta(IncidentListSerializer.Meta):
        fields = [
            *IncidentListSerializer.Meta.fields,
            "description",
            "acknowledged_at",
            "resolved_at",
            "closed_at",
        ]
        read_only_fields = fields


def _assignee_field():
    return serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True
    )


class IncidentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    priority = serializers.ChoiceField(choices=Priority.choices, default=Priority.MEDIUM)
    assignee_id = _assignee_field()

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Title cannot be blank.")
        return value


class IncidentUpdateSerializer(serializers.Serializer):
    """PATCH body. Status and assignee have their own endpoints, so they are rejected here."""

    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    priority = serializers.ChoiceField(choices=Priority.choices, required=False)

    REDIRECTS = {
        "status": "Use POST /incidents/{id}/transition/ to change status.",
        "assignee_id": "Use POST /incidents/{id}/assign/ to change the assignee.",
        "assignee": "Use POST /incidents/{id}/assign/ to change the assignee.",
    }

    def validate(self, attrs):
        errors = {k: msg for k, msg in self.REDIRECTS.items() if k in self.initial_data}
        if errors:
            raise serializers.ValidationError(errors)
        if not attrs:
            raise serializers.ValidationError(
                "Provide at least one of: title, description, priority."
            )
        if "title" in attrs and not attrs["title"].strip():
            raise serializers.ValidationError({"title": "Title cannot be blank."})
        return attrs


class AssignSerializer(serializers.Serializer):
    assignee_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), allow_null=True)


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")


class CommentSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "author", "body", "created_at", "edited_at"]
        read_only_fields = ["id", "author", "created_at", "edited_at"]

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Comment cannot be blank.")
        return value


class IncidentEventSerializer(serializers.ModelSerializer):
    actor = UserSummarySerializer(read_only=True)

    class Meta:
        model = IncidentEvent
        fields = ["id", "event_type", "actor", "data", "created_at"]
        read_only_fields = fields


class SLAPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = SLAPolicy
        fields = [
            "priority",
            "response_minutes",
            "resolution_minutes",
            "reminder_interval_minutes",
            "updated_at",
        ]
        read_only_fields = ["priority", "updated_at"]

    def validate(self, attrs):
        respond = attrs.get("response_minutes", getattr(self.instance, "response_minutes", None))
        resolve = attrs.get(
            "resolution_minutes", getattr(self.instance, "resolution_minutes", None)
        )
        if respond is not None and respond < 1:
            raise serializers.ValidationError({"response_minutes": "Must be at least 1 minute."})
        if respond and resolve and resolve < respond:
            raise serializers.ValidationError(
                {"resolution_minutes": "Must not be shorter than the response target."}
            )
        return attrs
