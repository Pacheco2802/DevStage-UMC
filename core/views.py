from django.shortcuts import get_object_or_404, render

from accounts.models import TermsVersion


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
