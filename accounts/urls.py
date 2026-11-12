from django.urls import include, path
from . import views

urlpatterns = [
    path("", include("django.contrib.auth.urls")),
    path("signup/estudante/", views.signup_student, name="signup_student"),
    path("signup/empresa/", views.signup_company, name="signup_company"),
    path("meus-dados/", views.my_data, name="my_data"),
    path("meus-dados/exportar/", views.my_data_export, name="my_data_export"),
    path("meus-dados/excluir/", views.my_data_delete, name="my_data_delete"),
    path("meus-dados/revogar-consentimento/", views.revoke_consent_view, name="revoke_consent"),
]
