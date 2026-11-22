from django.contrib.auth.views import LoginView
from django.urls import include, path

from . import views
from .forms import LoginForm

urlpatterns = [
    # Vem antes do include: o login usa o formulário com o aviso de bloqueio por tentativas
    path("login/", LoginView.as_view(authentication_form=LoginForm), name="login"),
    path("", include("django.contrib.auth.urls")),
    path("signup/estudante/", views.signup_student, name="signup_student"),
    path("signup/empresa/", views.signup_company, name="signup_company"),
    path("termos/aceitar/", views.terms_accept, name="terms_accept"),
    path("meus-dados/", views.my_data, name="my_data"),
    path("meus-dados/exportar/", views.my_data_export, name="my_data_export"),
    path("meus-dados/excluir/", views.my_data_delete, name="my_data_delete"),
    path("meus-dados/revogar-consentimento/", views.revoke_consent_view, name="revoke_consent"),
]
