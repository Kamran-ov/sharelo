from django.urls import path

from ledger.api import views

urlpatterns = [
    path("groups/", views.GroupListView.as_view()),
    path("groups/<int:group_id>/", views.GroupDetailView.as_view()),
    path("groups/<int:group_id>/link", views.LinkView.as_view()),
    path("join/<str:token>/", views.JoinView.as_view()),
    path("categories/", views.CategoryListView.as_view()),
    path("groups/<int:group_id>/category-defaults/", views.CategoryDefaultsView.as_view()),
    path("groups/<int:group_id>/expenses/", views.ExpenseListView.as_view()),
    path("groups/<int:group_id>/expenses/<int:eid>/", views.ExpenseDetailView.as_view()),
    path("groups/<int:group_id>/rate/", views.RateView.as_view()),
    path("groups/<int:group_id>/balances/", views.BalancesView.as_view()),
    path("groups/<int:group_id>/settlements/", views.SettlementListView.as_view()),
    path("groups/<int:group_id>/move-to-home", views.MoveToHomeView.as_view()),
    path("groups/<int:group_id>/recurring/", views.RuleListView.as_view()),
    path("groups/<int:group_id>/recurring/<int:rid>/", views.RuleDetailView.as_view()),
    path("groups/<int:group_id>/recurring/<int:rid>/pause", views.PauseView.as_view()),
    path("groups/<int:group_id>/recurring/<int:rid>/resume", views.ResumeView.as_view()),
    path("groups/<int:group_id>/recurring/<int:rid>/skip", views.SkipView.as_view()),
]
