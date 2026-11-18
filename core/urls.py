from django.urls import path

from . import views

app_name = "core"

# Sem versão na URL, mostra a vigente; com versão, mostra a publicada naquele número
urlpatterns = [
    path("termos/", views.legal_document, {"document": "terms"}, name="terms"),
    path("termos/<str:version>/", views.legal_document, {"document": "terms"}, name="terms_version"),
    path("privacidade/", views.legal_document, {"document": "privacy"}, name="privacy"),
    path("privacidade/<str:version>/", views.legal_document, {"document": "privacy"}, name="privacy_version"),
]
