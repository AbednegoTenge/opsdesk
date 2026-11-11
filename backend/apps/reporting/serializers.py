from datetime import timedelta

from rest_framework import serializers

from .models import IncidentReport

MAX_ADHOC_DAYS = 366


class IncidentReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentReport
        fields = [
            "id",
            "kind",
            "period_start",
            "period_end",
            "status",
            "data",
            "error",
            "requested_by",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields


class ReportListSerializer(IncidentReportSerializer):
    class Meta(IncidentReportSerializer.Meta):
        fields = [f for f in IncidentReportSerializer.Meta.fields if f != "data"]
        read_only_fields = fields


class ReportRequestSerializer(serializers.Serializer):
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()

    def validate(self, attrs):
        start, end = attrs["period_start"], attrs["period_end"]
        if end <= start:
            raise serializers.ValidationError({"period_end": "Must be after period_start."})
        if end - start > timedelta(days=MAX_ADHOC_DAYS):
            raise serializers.ValidationError(
                {"period_end": f"A report can cover at most {MAX_ADHOC_DAYS} days."}
            )
        return attrs
