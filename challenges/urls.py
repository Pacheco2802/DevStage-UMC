from django.urls import path

from . import views

app_name = "challenges"

urlpatterns = [
    path("", views.challenge_list, name="list"),
    path("<int:pk>/", views.challenge_detail, name="detail"),
    path("novo/", views.challenge_create, name="create"),
    path("meus/", views.my_challenges, name="mine"),
    path("<int:pk>/editar/", views.challenge_edit, name="edit"),
    path("<int:pk>/submissoes/", views.challenge_submissions, name="submissions"),
    path("minhas-submissoes/", views.my_submissions, name="my_submissions"),
    path("submissoes/<int:pk>/avaliar/", views.submission_evaluate, name="evaluate"),
]
