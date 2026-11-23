from django.shortcuts import get_object_or_404, render

from accounts.models import TermsVersion


def help_page(request):
    """Ajuda do sistema: o passo a passo de cada perfil, na ordem do manual, e o manual completo
    em PDF. É pública, para que o visitante também consiga tirar dúvidas antes de criar a conta."""
    return render(request, "core/help.html")


def legal_document(request, document, version=None):
    """Termos de Uso ou Política de Privacidade: a versão vigente ou, se pedida na URL, uma anterior.
    `document` é "terms" ou "privacy" e vem fixo do urls.py; o texto está em core/legal/<versão>/."""
    current = TermsVersion.current()
    terms = get_object_or_404(TermsVersion, version=version) if version else current
    return render(request, f"core/legal/{terms.version}/{document}.html", {
        "document": document,
        "terms": terms,
        "is_current": terms == current,
        "versions": TermsVersion.objects.all(),
    })
