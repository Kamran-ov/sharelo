from django.urls import path

from importers.api import views

urlpatterns = [
    path("groups/<int:group_id>/bank-imports/", views.BankImportListView.as_view()),
    path(
        "groups/<int:group_id>/bank-imports/<int:batch_id>/",
        views.BankImportDetailView.as_view(),
    ),
    path("groups/<int:group_id>/bank-rows/", views.ReviewListView.as_view()),
    path("groups/<int:group_id>/bank-rows/<int:row_id>/resolve", views.ResolveView.as_view()),
    path("groups/<int:group_id>/bank-rows/<int:row_id>/undo", views.UndoView.as_view()),
    path("groups/<int:group_id>/shop-rules/", views.ShopRuleListView.as_view()),
    path("groups/<int:group_id>/shop-rules/<int:rule_id>/", views.ShopRuleDetailView.as_view()),
]
