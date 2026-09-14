from django import forms
from .models import Submission

class SubmissionForm(forms.ModelForm):
      class Meta:
          model = Submission
          fields = ["repo_url", "deploy_url", "description"]

