from django.urls import path

from apps.users import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="auth-register"),
    path("token/", views.LoginView.as_view(), name="auth-token"),
    path("token/refresh/", views.RefreshView.as_view(), name="auth-token-refresh"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path("password/change/", views.PasswordChangeView.as_view(), name="auth-password-change"),
]
