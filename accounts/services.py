from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog
from challenges.models import Challenge
from core.utils import get_client_ip, get_user_agent

from .models import ConsentLog


def record_consent(user, request):
    """Guarda a evidência do aceite: versão dos termos, IP e navegador."""
    return ConsentLog.objects.create(
        user=user,
        terms_version=settings.LGPD_TERMS_VERSION,
        ip=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


def revoke_consent(user):
    """Revogação (art. 8º, §5º): fecha os aceites ativos e desativa a conta,
    já que sem consentimento não há base legal para continuar tratando os dados."""
    user.consents.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
    user.is_active = False
    user.save(update_fields=["is_active"])


@transaction.atomic
def anonymize_user(user):
    """Eliminação (art. 18, VI) por anonimização: remove o que identifica o titular,
    mas mantém desafios/submissões para não quebrar dados de outros usuários."""
    revoke_consent(user)

    user.username = f"removido-{user.pk}"
    user.first_name = ""
    user.last_name = ""
    user.email = ""
    user.set_unusable_password()
    user.is_active = False
    user.save()

    if user.role == user.Role.COMPANY and hasattr(user, "company_profile"):
        profile = user.company_profile
        profile.company_name = f"Empresa removida #{profile.pk}"
        profile.save()
        # Sem empresa para avaliar, desafios abertos são encerrados
        profile.challenges.filter(status=Challenge.Status.OPEN).update(status=Challenge.Status.CLOSED)


def export_user_data(user):
    """Portabilidade (art. 18, V): todos os dados do titular em estrutura serializável."""
    data = {
        "exportado_em": timezone.now().isoformat(),
        "versao_termos_vigente": settings.LGPD_TERMS_VERSION,
        "usuario": {
            "username": user.username,
            "email": user.email,
            "nome": user.first_name,
            "sobrenome": user.last_name,
            "perfil": user.get_role_display(),
            "cadastrado_em": user.date_joined.isoformat(),
            "ultimo_login": user.last_login.isoformat() if user.last_login else None,
        },
        "consentimentos": [
            {
                "versao_termos": c.terms_version,
                "aceito_em": c.accepted_at.isoformat(),
                "ip": c.ip,
                "user_agent": c.user_agent,
                "revogado_em": c.revoked_at.isoformat() if c.revoked_at else None,
            }
            for c in user.consents.all()
        ],
        "submissoes": [
            {
                "desafio": s.challenge.title,
                "repo_url": s.repo_url,
                "deploy_url": s.deploy_url,
                "descricao": s.description,
                "enviada_em": s.submitted_at.isoformat(),
            }
            for s in user.submissions.select_related("challenge")
        ],
        "registros_auditoria": [
            {
                "acao": log.get_action_display(),
                "caminho": log.path,
                "ip": log.ip,
                "data": log.timestamp.isoformat(),
            }
            for log in AuditLog.objects.filter(user=user)
        ],
    }

    if hasattr(user, "company_profile"):
        profile = user.company_profile
        data["empresa"] = {
            "nome": profile.company_name,
            "aprovada": profile.approved,
            "desafios_publicados": [
                {"titulo": ch.title, "status": ch.get_status_display(), "prazo": ch.deadline.isoformat()}
                for ch in profile.challenges.all()
            ],
        }

    return data
