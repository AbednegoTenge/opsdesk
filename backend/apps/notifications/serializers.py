from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    incident_reference = serializers.CharField(source="incident.reference", default=None)

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "title",
            "body",
            "incident",
            "incident_reference",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields


class MarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get("all") and not attrs.get("ids"):
            raise serializers.ValidationError("Provide 'ids' or set 'all' to true.")
        return attrs
