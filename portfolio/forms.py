from django import forms

from accounts.models import StudentProfile


class StudentProfileForm(forms.ModelForm):
    """Meu perfil (RF15): o que o estudante escolhe mostrar no portfólio."""

    class Meta:
        model = StudentProfile
        fields = ["bio", "github_username", "portfolio_public"]
        labels = {
            "bio": "Apresentação",
            "github_username": "Usuário do GitHub",
            "portfolio_public": "Portfólio público",
        }
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4, "maxlength": 500}),
        }
