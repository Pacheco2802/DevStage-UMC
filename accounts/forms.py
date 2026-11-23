from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from core.utils import get_client_ip

from . import throttle
from .models import CompanyProfile, StudentProfile, User


class StudentSignupForm(UserCreationForm):
    # Campo extra
    accept_lgpd = forms.BooleanField(
        required=True,
        label="Li e aceito os termos de uso e a política de privacidade",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        # Adiciona o campo extra aos campos do formulário
        fields = ("username", "email", "first_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "STUDENT"  # Define usuário como "STUDENT"
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            # Perfil do portfólio, público por padrão (RN53); a view grava tudo na mesma transação
            StudentProfile.objects.create(user=user)
        return user

class CompanySignupForm(UserCreationForm):
    company_name = forms.CharField(
        max_length=200,
        label="Nome da empresa",
    )
    accept_lgpd = forms.BooleanField(
        required=True,
        label="Li e aceito os termos de uso e a política de privacidade",
    )
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "COMPANY"  # Define usuário como "COMPANY"
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            CompanyProfile.objects.create(
                user=user,
                company_name=self.cleaned_data["company_name"],
                # appproved fica no default false do model
            )
        return user


class LoginForm(AuthenticationForm):
    """Formulário de login que avisa quando o acesso está bloqueado por excesso de tentativas.
    Quem aplica o bloqueio é o backend de autenticação; aqui ele só ganha uma mensagem clara."""

    def clean(self):
        minutos = throttle.minutos_de_bloqueio(self.cleaned_data.get("username"), get_client_ip(self.request))
        if minutos:
            raise forms.ValidationError(
                f"Muitas tentativas de login. Por segurança, o acesso está bloqueado. "
                f"Tente novamente em {minutos} minuto{'s' if minutos > 1 else ''}.",
                code="bloqueado",
            )
        return super().clean()


class TermsAcceptForm(forms.Form):
    """Novo aceite quando uma versão dos termos é publicada: a caixa marcada é validada no servidor."""
    accept_lgpd = forms.BooleanField(
        required=True,
        label="Li e aceito os termos de uso e a política de privacidade",
    )


class MyDataForm(forms.ModelForm):
    """Correção de dados cadastrais (art. 18, III)."""
    email = forms.EmailField(required=True, label="E-mail")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {"first_name": "Nome", "last_name": "Sobrenome"}


class CompanyDataForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ["company_name"]
        labels = {"company_name": "Nome da empresa"}
