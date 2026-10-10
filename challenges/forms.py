from django import forms
from .models import Submission, Challenge
from django.core.exceptions import ValidationError
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
          