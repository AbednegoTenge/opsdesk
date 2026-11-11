from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import IsAdmin, IsEngineerOrAdmin

from . import services
from .models import IncidentReport, ReportKind
from .serializers import IncidentReportSerializer, ReportListSerializer, ReportRequestSerializer


class ReportViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = IncidentReport.objects.all()

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated(), IsEngineerOrAdmin()]

    def get_serializer_class(self):
        return ReportListSerializer if self.action == "list" else IncidentReportSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if kind := self.request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        return qs

    @extend_schema(
        request=ReportRequestSerializer,
        responses={202: IncidentReportSerializer, 200: IncidentReportSerializer},
    )
    def create(self, request):
        """Queue an on-demand report. Returns 202 at once; poll GET /reports/{id}/."""
        s = ReportRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        report, created = services.request_report(
            ReportKind.ADHOC,
            s.validated_data["period_start"],
            s.validated_data["period_end"],
            requested_by=request.user,
        )
        return Response(
            IncidentReportSerializer(report).data,
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )
