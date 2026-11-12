from django.urls import path

from . import views

app_name = "portfolio"

urlpatterns = [
    path("ranking/", views.ranking, name="ranking"),
    path("<str:username>/", views.student_portfolio, name="detail"),
]
