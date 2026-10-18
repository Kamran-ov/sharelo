from django.urls import path

from accounts.api import views

urlpatterns = [
    path("auth/register", views.RegisterView.as_view()),
    path("auth/login", views.LoginView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("auth/google", views.GoogleView.as_view()),
    path("me", views.MeView.as_view()),
]
