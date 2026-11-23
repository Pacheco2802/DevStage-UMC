from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from integrations.github_client import repo_exists

from .models import Challenge, Evaluation, Submission


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["repo_url", "deploy_url", "description"]

    # Resposta do GitHub sobre o repositório, guardada para o raio-X não consultar de novo
    repo_info = None

    def clean_repo_url(self):
        url = self.cleaned_data["repo_url"]
        result = repo_exists(url)
        if not result.valid:
            raise ValidationError(result.reason)
        self.repo_info = result.data
        return url

class ChallengeForm(forms.ModelForm):
    """Criação e edição do desafio. A situação só é escolhida na criação (Rascunho ou Aberto);
    depois disso ela muda pelas ações Publicar e Encerrar, que seguem o ciclo de vida (RN21)."""

    class Meta:
        model = Challenge
        fields = ["title", "description", "difficulty", "deadline", "status"]
        labels = {
            "title": "Título",
            "description": "Descrição",
            "difficulty": "Nível de dificuldade",
            "deadline": "Prazo de entrega",
            "status": "Situação inicial",
        }
        widgets = {
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["status"]
            # O input datetime-local só aceita "AAAA-MM-DDTHH:MM"; sem isso o prazo vem vazio na edição
            if not self.is_bound:
                self.initial["deadline"] = timezone.localtime(self.instance.deadline).strftime("%Y-%m-%dT%H:%M")
        else:
            # RN20: um desafio novo começa como Rascunho ou já Aberto, nunca Encerrado
            self.fields["status"].choices = [
                choice for choice in Challenge.Status.choices if choice[0] != Challenge.Status.CLOSED
            ]

    def clean_deadline(self):
        deadline = self.cleaned_data["deadline"]
        # RN19: o prazo precisa estar no futuro. Na edição, só é conferido se foi alterado,
        # para que corrigir o título de um desafio não esbarre em um prazo já definido.
        changed = not self.instance.pk or deadline != self.instance.deadline
        if changed and deadline <= timezone.now():
            raise ValidationError("O prazo precisa ser uma data futura.")
        return deadline


class EvaluationForm(forms.ModelForm):
    # RN42: a faixa é conferida aqui, nos validadores do modelo e numa restrição do banco
    score = forms.IntegerField(min_value=0, max_value=100, label="Nota (0 a 100)")

    class Meta:
        model = Evaluation
        fields = ["score", "strengths", "improvements"]
        labels = {
            "strengths": "Pontos fortes",
            "improvements": "Pontos a melhorar",
        }
        widgets = {
            "strengths": forms.Textarea(attrs={"rows": 4}),
            "improvements": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No banco o campo aceita vazio por causa das avaliações antigas; no formulário é obrigatório
        self.fields["improvements"].required = True

    def _clean_feedback(self, field):
        # RN43: cada parte do feedback precisa ter conteúdo, não só uma palavra
        text = self.cleaned_data[field].strip()
        if len(text) < Evaluation.MIN_FEEDBACK_LENGTH:
            raise ValidationError(f"Escreva pelo menos {Evaluation.MIN_FEEDBACK_LENGTH} caracteres.")
        return text

    def clean_strengths(self):
        return self._clean_feedback("strengths")

    def clean_improvements(self):
        return self._clean_feedback("improvements")
