from django.urls import path

from . import views

app_name = "portfolio"

# As rotas fixas vêm antes de <username>, que aceita qualquer texto
urlpatterns = [
    path("ranking/", views.ranking, name="ranking"),
    path("meu-perfil/", views.edit_profile, name="edit_profile"),
    path("<str:username>/", views.student_portfolio, name="detail"),
]
