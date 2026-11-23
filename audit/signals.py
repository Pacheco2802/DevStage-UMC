from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from accounts.models import CompanyProfile, ConsentLog, StudentProfile
from challenges.models import Challenge, Evaluation, Submission
from core.utils import get_client_ip

from .middleware import current_actor
from .models import AuditLog

User = get_user_model()

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.LOGIN,
        path=request.path if request else "",
        ip=get_client_ip(request),
    )

@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.LOGOUT,
        path=request.path if request else "",
        ip=get_client_ip(request),
    )

# Campos em que a alteração guarda o valor anterior e o novo: a nota corrigida pelo administrador
# (RN44) e as condições do desafio (RN21 e RN22). Textos longos e dados pessoais ficam de fora.
TRACKED_FIELDS = {
    Evaluation: ["score", "points"],
    Challenge: ["status", "difficulty", "deadline"],
}


def _remember_previous(sender, instance, **kwargs):
    """Antes de gravar, guarda no próprio objeto o que está no banco nos campos acompanhados."""
    instance._audit_previous = None
    if instance.pk:
        instance._audit_previous = sender.objects.filter(pk=instance.pk).values(*TRACKED_FIELDS[sender]).first()


def _changes(sender, instance):
    previous = getattr(instance, "_audit_previous", None)
    if not previous:
        return {}
    changes = {}
    for field, old in previous.items():
        new = getattr(instance, field)
        if old != new:
            # Datas viram texto para caber no JSON
            changes[field] = [value.isoformat() if hasattr(value, "isoformat") else value for value in [old, new]]
    return changes


def _log_save(sender, instance, created, **kwargs):
    # O sinal não recebe a requisição; quem fez a ação vem do AuditMiddleware (RN60)
    AuditLog.objects.create(
        action=AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE,
        target_model=sender.__name__,
        target_id=str(instance.pk),
        changes={} if created else _changes(sender, instance),
        **current_actor(),
    )

def _log_delete(sender, instance, **kwargs):
    AuditLog.objects.create(
        action=AuditLog.Action.DELETE,
        target_model=sender.__name__,
        target_id=str(instance.pk),
        **current_actor(),
    )

for model in (User, CompanyProfile, StudentProfile, Challenge, Submission, Evaluation, ConsentLog):
    post_save.connect(_log_save, sender=model)
    post_delete.connect(_log_delete, sender=model)

for model in TRACKED_FIELDS:
    pre_save.connect(_remember_previous, sender=model)
