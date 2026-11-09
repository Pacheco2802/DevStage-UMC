from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, CompanyProfile
from django.db import transaction

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
