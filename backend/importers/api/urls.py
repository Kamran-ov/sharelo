from django.urls import path

from importers.api import views

urlpatterns = [
    path("groups/<int:group_id>/bank-imports/", views.BankImportListView.as_view()),
    path(
        "groups/<int:group_id>/bank-imports/<int:batch_id>/",
        views.BankImportDetailView.as_view(),
    ),
]
