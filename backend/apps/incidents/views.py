from contextlib import contextmanager

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import IsAdmin, IsEngineerOrAdmin, ReadOnlyOrEngineer

from . import services
from .filters import IncidentFilterSerializer, filter_incidents, with_priority_rank
from .models import Comment, Incident, SLAPolicy
from .serializers import (
    AssignSerializer,
    CommentSerializer,
    IncidentCreateSerializer,
    IncidentDetailSerializer,
    IncidentEventSerializer,
    IncidentListSerializer,
    IncidentUpdateSerializer,
    SLAPolicySerializer,
    TransitionSerializer,
)


@contextmanager
def rule_errors():
    """Turn service-layer rule violations into API errors."""
    try:
        yield
    except services.IncidentRuleError as exc:
        if exc.code in ("forbidden", "forbidden_transition"):
            raise PermissionDenied(exc.message) from exc
        detail = {exc.field: [exc.message]} if exc.field else [exc.message]
        raise ValidationError(detail, code=exc.code) from exc


class IncidentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Incident.objects.select_related("reporter", "assignee")
    http_method_names = ["get", "post", "patch", "delete", "options"]

    def get_permissions(self):
        if self.action == "destroy":
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated(), ReadOnlyOrEngineer()]

    def get_serializer_class(self):
        if self.action == "list":
            return IncidentListSerializer
        return IncidentDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            qs = filter_incidents(qs, self.request.query_params, self.request.user)
        return qs

    def _detail(self, incident, status_code=status.HTTP_200_OK):
        incident = self.get_queryset().get(pk=incident.pk)
        return Response(IncidentDetailSerializer(incident).data, status=status_code)

    @extend_schema(parameters=[IncidentFilterSerializer])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=IncidentCreateSerializer, responses={201: IncidentDetailSerializer})
    def create(self, request):
        s = IncidentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        with rule_errors():
            incident = services.create_incident(
                actor=request.user,
                title=data["title"],
                description=data.get("description", ""),
                priority=data["priority"],
                assignee=data.get("assignee_id"),
            )
        return self._detail(incident, status.HTTP_201_CREATED)

    @extend_schema(request=IncidentUpdateSerializer, responses=IncidentDetailSerializer)
    def partial_update(self, request, pk=None):
        incident = self.get_object()
        s = IncidentUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with rule_errors():
            incident = services.update_incident(
                incident_id=incident.pk, actor=request.user, **s.validated_data
            )
        return self._detail(incident)

    def destroy(self, request, pk=None):
        incident = self.get_object()
        services.delete_incident(incident_id=incident.pk, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=AssignSerializer, responses=IncidentDetailSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        incident = self.get_object()
        s = AssignSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with rule_errors():
            incident = services.assign_incident(
                incident_id=incident.pk,
                actor=request.user,
                assignee=s.validated_data["assignee_id"],
            )
        return self._detail(incident)

    @extend_schema(request=TransitionSerializer, responses=IncidentDetailSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        incident = self.get_object()
        s = TransitionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with rule_errors():
            incident = services.transition_incident(
                incident_id=incident.pk,
                actor=request.user,
                to_status=s.validated_data["status"],
                note=s.validated_data["note"],
            )
        return self._detail(incident)

    @extend_schema(methods=["GET"], responses=CommentSerializer(many=True))
    @extend_schema(methods=["POST"], request=CommentSerializer, responses={201: CommentSerializer})
    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        incident = self.get_object()
        if request.method == "GET":
            qs = incident.comments.select_related("author")
            page = self.paginate_queryset(qs)
            return self.get_paginated_response(CommentSerializer(page, many=True).data)
        s = CommentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        comment = services.add_comment(
            incident_id=incident.pk, actor=request.user, body=s.validated_data["body"]
        )
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=IncidentEventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        incident = self.get_object()
        page = self.paginate_queryset(incident.events.select_related("actor"))
        return self.get_paginated_response(IncidentEventSerializer(page, many=True).data)


class CommentViewSet(mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """PATCH / DELETE /incidents/{incident_pk}/comments/{pk}/ - author or Admin only."""

    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsEngineerOrAdmin]
    http_method_names = ["patch", "delete", "options"]

    def get_object(self):
        return get_object_or_404(
            Comment, pk=self.kwargs["pk"], incident_id=self.kwargs["incident_pk"]
        )

    def partial_update(self, request, incident_pk=None, pk=None):
        comment = self.get_object()
        s = CommentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with rule_errors():
            comment = services.edit_comment(
                comment_id=comment.pk, actor=request.user, body=s.validated_data["body"]
            )
        return Response(CommentSerializer(comment).data)

    def destroy(self, request, incident_pk=None, pk=None):
        comment = self.get_object()
        with rule_errors():
            services.delete_comment(comment_id=comment.pk, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SLAPolicyViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = SLAPolicy.objects.all()
    serializer_class = SLAPolicySerializer
    lookup_field = "priority"
    pagination_class = None
    http_method_names = ["get", "put", "patch", "options"]

    def get_permissions(self):
        if self.action in ("update", "partial_update"):
            return [IsAuthenticated(), IsAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return with_priority_rank(super().get_queryset()).order_by("priority_rank")
