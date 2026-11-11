from rest_framework.routers import SimpleRouter

from .views import ReportViewSet

router = SimpleRouter()
router.register("reports", ReportViewSet, basename="report")

urlpatterns = router.urls
