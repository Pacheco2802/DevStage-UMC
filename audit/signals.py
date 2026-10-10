from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from accounts.models import CompanyProfile
from challenges.models import Challenge, Submission
from .models import AuditLog

User = get_user_model()

def _get_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.LOGIN,
        path=request.path if request else "",
        ip=_get_ip(request),
    )

@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.LOGOUT,
        path=request.path if request else "",
        ip=_get_ip(request),
    )

def _log_save(sender, instance, created, **kwargs):
    AuditLog.objects.create(
        user=None,  # signals de model não têm acesso ao request
        action=AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE,
        target_model=sender.__name__,
        target_id=str(instance.pk),
    )

def _log_delete(sender, instance, **kwargs):
    AuditLog.objects.create(
        user=None,
        action=AuditLog.Action.DELETE,
        target_model=sender.__name__,
        target_id=str(instance.pk),
    )

for model in (User, CompanyProfile, Challenge, Submission):
    post_save.connect(_log_save, sender=model)
    post_delete.connect(_log_delete, sender=model)