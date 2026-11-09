from django import forms
from .models import Submission, Challenge, Evaluation
from django.core.exceptions import ValidationError
from django.utils import timezone
from integrations.github_client import repo_exists

class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ["repo_url", "deploy_url", "description"]
    def clean_repo_url(self):
        url = self.cleaned_data["repo_url"]
        result = repo_exists(url)
        if not result.valid:
            raise ValidationError(result.reason)
        return url

class ChallengeForm(forms.ModelForm):
    class Meta:
        model = Challenge
        fields = ["title", "description", "deadline", "status"]
        widgets = {
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # O input datetime-local só aceita "AAAA-MM-DDTHH:MM"; sem isso o prazo vem vazio na edição
        if self.instance.pk and not self.is_bound:
            self.initial["deadline"] = timezone.localtime(self.instance.deadline).strftime("%Y-%m-%dT%H:%M")


class EvaluationForm(forms.ModelForm):
    class Meta:
        model = Evaluation
        fields = ["score", "feedback"]
        labels = {"score": "Nota (0 a 10)", "feedback": "Feedback para o estudante"}
        widgets = {
            "score": forms.NumberInput(attrs={"min": 0, "max": 10}),
            "feedback": forms.Textarea(attrs={"rows": 6}),
        }

    def clean_feedback(self):
        feedback = self.cleaned_data["feedback"].strip()
        if len(feedback) < 10:
            raise ValidationError("Escreva um feedback com pelo menos 10 caracteres.")
        return feedback
