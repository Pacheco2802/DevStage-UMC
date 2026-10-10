from django.urls import path
from . import views

app_name = "challenges"

urlpatterns = [
    path("", views.challenge_list, name="list"),
    path("<int:pk>/", views.challenge_detail, name="detail"),
    path("novo/", views.challenge_create, name="create"),
]
