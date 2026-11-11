from rest_framework.routers import SimpleRouter

from apps.users.views import UserViewSet

router = SimpleRouter()
router.register("", UserViewSet, basename="user")

urlpatterns = router.urls
