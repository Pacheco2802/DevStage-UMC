from django.db import models
from django.conf import settings

# Create your models here.
class Challenge(models.Model):
      class Status(models.TextChoices):
          DRAFT = "DRAFT", "Rascunho"
          OPEN = "OPEN", "Aberto"
          CLOSED = "CLOSED", "Encerrado"

      company = models.ForeignKey(
          "accounts.CompanyProfile",
          on_delete=models.CASCADE,
          related_name="challenges",
      )
      title = models.CharField(max_length=200)
      description = models.TextField()
      deadline = models.DateTimeField()
      status = models.CharField(
          max_length=10,
          choices=Status.choices,
          default=Status.DRAFT,
      )
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      def __str__(self):
          return self.title

class Submission(models.Model):
    challenge = models.ForeignKey(
            Challenge,
            on_delete=models.CASCADE,
            related_name="submissions",
        )
    student = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            on_delete=models.CASCADE,
            related_name="submissions",
            )
    repo_url = models.URLField(max_length=500)
    deploy_url = models.URLField(max_length=500, blank=True)
    description = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge", "student"],
                name="unique_submission_per_student_per_challenge"
            ),
        ]
        ordering = ["-submitted_at"]
    def __str__(self):
          return f"{self.student.username} → {self.challenge.title}"
