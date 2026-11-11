from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CommentViewSet, IncidentViewSet, SLAPolicyViewSet

router = SimpleRouter()
router.register("incidents", IncidentViewSet, basename="incident")
router.register("sla-policies", SLAPolicyViewSet, basename="sla-policy")

comment_detail = CommentViewSet.as_view({"patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path(
        "incidents/<int:incident_pk>/comments/<int:pk>/",
        comment_detail,
        name="incident-comment-detail",
    ),
    *router.urls,
]
