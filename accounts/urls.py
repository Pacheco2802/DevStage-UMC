from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    # O login usa o formulário com o aviso de bloqueio por tentativas
    path("login/", LoginView.as_view(authentication_form=LoginForm), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # As rotas de troca e de recuperação de senha do Django não são incluídas: o sistema ainda não
    # envia e-mail, e a tela de recuperação responderia "enviado" sem enviar nada
    path("signup/estudante/", views.signup_student, name="signup_student"),
    path("signup/empresa/", views.signup_company, name="signup_company"),
    path("termos/aceitar/", views.terms_accept, name="terms_accept"),
    path("meus-dados/", views.my_data, name="my_data"),
    path("meus-dados/exportar/", views.my_data_export, name="my_data_export"),
    path("meus-dados/excluir/", views.my_data_delete, name="my_data_delete"),
    path("meus-dados/revogar-consentimento/", views.revoke_consent_view, name="revoke_consent"),
]
