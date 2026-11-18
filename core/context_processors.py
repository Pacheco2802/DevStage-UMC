from django.conf import settings


def lgpd(request):
    # Deixa o contato do DPO disponível em todos os templates
    return {
        "DPO_NAME": settings.DPO_NAME,
        "DPO_EMAIL": settings.DPO_EMAIL,
    }
