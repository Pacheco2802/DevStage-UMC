from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="index"),
    path("api/dados/", views.DashboardDataAPI.as_view(), name="api_dados"),
]
