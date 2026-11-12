from django.conf import settings


def lgpd(request):
    # Deixa versão dos termos e contato do DPO disponíveis em todos os templates
    return {
        "LGPD_TERMS_VERSION": settings.LGPD_TERMS_VERSION,
        "DPO_NAME": settings.DPO_NAME,
        "DPO_EMAIL": settings.DPO_EMAIL,
    }
