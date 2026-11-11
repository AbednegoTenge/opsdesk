from rest_framework.routers import SimpleRouter

from .views import DashboardViewSet, ReportViewSet

router = SimpleRouter()
router.register("reports", ReportViewSet, basename="report")
router.register("dashboard", DashboardViewSet, basename="dashboard")

urlpatterns = router.urls
