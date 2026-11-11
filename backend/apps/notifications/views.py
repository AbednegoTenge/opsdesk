from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import MarkReadSerializer, NotificationSerializer


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The current user's in-app notifications. Nobody can see anyone else's."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user).select_related("incident")
        if self.request.query_params.get("unread", "").lower() in ("1", "true", "yes"):
            qs = qs.filter(read_at__isnull=True)
        return qs

    @extend_schema(parameters=[OpenApiParameter("unread", bool, description="Only unread")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses=inline_serializer("UnreadCount", {"unread": serializers.IntegerField()})
    )
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()
        return Response({"unread": count})

    @extend_schema(
        request=MarkReadSerializer,
        responses=inline_serializer("MarkReadResult", {"updated": serializers.IntegerField()}),
    )
    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request):
        s = MarkReadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        qs = Notification.objects.filter(recipient=request.user, read_at__isnull=True)
        if not s.validated_data["all"]:
            qs = qs.filter(pk__in=s.validated_data["ids"])
        return Response({"updated": qs.update(read_at=timezone.now())})
