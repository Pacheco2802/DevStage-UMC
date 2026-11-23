from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from integrations.github_client import parse_repo_url


# Create your models here.
class Challenge(models.Model):
      class Status(models.TextChoices):
          DRAFT = "DRAFT", "Rascunho"
          OPEN = "OPEN", "Aberto"
          CLOSED = "CLOSED", "Encerrado"

      class Difficulty(models.TextChoices):
          BEGINNER = "BEGINNER", "Iniciante"
          INTERMEDIATE = "INTERMEDIATE", "Intermediário"
          ADVANCED = "ADVANCED", "Avançado"

      # Peso de cada dificuldade no cálculo dos pontos: pontos = nota x peso (RN45)
      DIFFICULTY_WEIGHTS = {
          Difficulty.BEGINNER: 1,
          Difficulty.INTERMEDIATE: 2,
          Difficulty.ADVANCED: 3,
      }

      # Ciclo de vida (RN21): cada situação só avança para a seguinte; Encerrado é final
      NEXT_STATUS = {
          Status.DRAFT: Status.OPEN,
          Status.OPEN: Status.CLOSED,
      }

      company = models.ForeignKey(
          "accounts.CompanyProfile",
          on_delete=models.CASCADE,
          related_name="challenges",
      )
      title = models.CharField(max_length=200)
      description = models.TextField()
      deadline = models.DateTimeField()
      difficulty = models.CharField(
          max_length=12,
          choices=Difficulty.choices,
          default=Difficulty.BEGINNER,
      )
      status = models.CharField(
          max_length=10,
          choices=Status.choices,
          default=Status.DRAFT,
      )
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      def __str__(self):
          return self.title

      @property
      def weight(self):
          return self.DIFFICULTY_WEIGHTS[self.difficulty]

      @property
      def deadline_passed(self):
          return self.deadline < timezone.now()

      def can_transition_to(self, new_status):
          return self.NEXT_STATUS.get(self.status) == new_status

      @property
      def is_editable(self):
          """RN22: depois da primeira entrega as condições do desafio ficam congeladas."""
          if self.status == self.Status.DRAFT:
              return True
          return self.status == self.Status.OPEN and not self.submissions.exists()

      @property
      def accepts_evaluation(self):
          """RN41: a avaliação só começa quando ninguém mais pode entregar,
          ou seja, com o prazo vencido ou o desafio encerrado pela empresa."""
          return self.status == self.Status.CLOSED or self.deadline_passed

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


class Evaluation(models.Model):
    """Avaliação da empresa: uma por submissão (OneToOne), nota de 0 a 100 e feedback em duas partes."""
    MIN_FEEDBACK_LENGTH = 20

    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name="evaluation",
    )
    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="evaluations_given",
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    strengths = models.TextField()
    improvements = models.TextField(blank=True)
    # Peso da dificuldade copiado do desafio quando a avaliação é criada: assim os pontos
    # não mudam se a dificuldade do desafio for alterada depois (RN46)
    weight = models.PositiveSmallIntegerField(editable=False)
    points = models.PositiveSmallIntegerField(editable=False)
    evaluated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Mesmo que alguém salve fora do form, o banco recusa nota fora da faixa
            models.CheckConstraint(
                condition=models.Q(score__gte=0) & models.Q(score__lte=100),
                name="evaluation_score_between_0_and_100",
            ),
        ]

    def __str__(self):
        return f"{self.submission} - nota {self.score}"

    def calculate_points(self):
        """RN45: pontos = nota x peso da dificuldade (de 0 a 300)."""
        return self.score * self.weight

    def save(self, *args, **kwargs):
        if self.weight is None:
            self.weight = self.submission.challenge.weight
        # Recalculado a cada gravação: se o administrador corrigir a nota, os pontos acompanham
        self.points = self.calculate_points()
        super().save(*args, **kwargs)


class RepoSnapshot(models.Model):
    """Raio-X da entrega: o commit registrado na submissão e a análise do repositório nesse commit.

    O commit é gravado pelo nosso servidor no momento da entrega, então o que o estudante
    enviar ao repositório depois disso não entra na avaliação."""
    class Status(models.TextChoices):
        PENDING = "PENDING", "Análise pendente"
        READY = "READY", "Analisado"
        ERROR = "ERROR", "Falha na análise"

    PRACTICES = [
        ["gitignore", ".gitignore"],
        ["license", "Licença"],
        ["docker", "Docker"],
        ["ci", "Pipeline de CI"],
        ["env_example", ".env de exemplo"],
    ]

    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name="snapshot",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    commit_sha = models.CharField(max_length=40, blank=True)
    main_language = models.CharField(max_length=40, blank=True)
    # report: linguagens, tecnologias, tamanho, README, testes, boas práticas, histórico e dados do repositório
    report = models.JSONField(default=dict)
    # alerts: lista de {"code": ..., "text": ...} com indícios para a empresa conferir
    alerts = models.JSONField(default=list)
    error_message = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Raio-X de {self.submission}"

    @property
    def commit_url(self):
        owner, repo = parse_repo_url(self.submission.repo_url)
        if not (owner and self.commit_sha):
            return ""
        return f"https://github.com/{owner}/{repo}/tree/{self.commit_sha}"

    @property
    def registered_late(self):
        """O commit não foi registrado no momento da entrega, e sim na primeira análise: o GitHub
        não respondeu na hora, ou a entrega é anterior a este recurso e a empresa pediu o raio-X."""
        if self.report.get("commit_from_analysis"):
            return True
        return self.created_at - self.submission.submitted_at > timedelta(minutes=10)

    @property
    def practices(self):
        present = self.report.get("practices", [])
        return [[label, code in present] for code, label in self.PRACTICES]
