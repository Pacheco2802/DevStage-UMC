from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


# Create your models here.
class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Estudante"
        COMPANY = "COMPANY", "Empresa"
        PLATFORM_ADMIN = "PLATFORM_ADMIN", "Administrador da Plataforma"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )

class CompanyProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_profile'
    )
    company_name = models.CharField(max_length=200)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.company_name


class StudentProfile(models.Model):
    """Dados do portfólio do estudante: apresentação, usuário do GitHub e visibilidade."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    bio = models.TextField(max_length=500, blank=True)
    github_username = models.CharField(
        max_length=39,
        blank=True,
        validators=[
            RegexValidator(
                r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$",
                "Informe apenas o nome de usuário do GitHub, sem @ e sem o endereço completo.",
            )
        ],
    )
    # RN53: o portfólio é público por padrão e o estudante pode torná-lo privado quando quiser
    portfolio_public = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Perfil de {self.user.username}"

    @classmethod
    def for_user(cls, user):
        """Perfil do estudante; contas criadas fora do cadastro (admin, por exemplo) ganham um agora."""
        profile, _ = cls.objects.get_or_create(user=user)
        return profile


class LoginAttempt(models.Model):
    """Tentativa de login que falhou. Serve só para o limite de tentativas (accounts/throttle.py)
    e é apagada depois de um dia."""
    username = models.CharField(max_length=150, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    failed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-failed_at"]

    def __str__(self):
        return f"{self.username} em {self.failed_at:%d/%m/%Y %H:%M}"


class TermsVersion(models.Model):
    """Versão publicada dos Termos de Uso e da Política de Privacidade.

    O texto de cada versão fica em templates (core/legal/<versão>/), versionado no git;
    aqui ficam a data de publicação e o resumo do que mudou. A mais recente é a vigente."""
    version = models.CharField(max_length=20, unique=True)
    published_at = models.DateTimeField()
    summary = models.TextField()

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return f"Termos v{self.version}"

    @classmethod
    def current(cls):
        return cls.objects.first()


class ConsentLog(models.Model):
    """Registro do aceite dos termos (LGPD art. 8º): quem aceitou, qual versão, quando e de onde."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consents",
    )
    terms_version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-accepted_at"]

    def __str__(self):
        return f"{self.user.username} - termos v{self.terms_version}"
