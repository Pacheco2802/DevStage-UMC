from django.shortcuts import redirect

from .services import has_current_consent


class TermsConsentMiddleware:
    """Usuário logado só navega depois de aceitar a versão vigente dos termos (LGPD art. 8º, § 6º)."""

    # Continuam abertas sem o aceite: ler os documentos, aceitar, sair e exercer os direitos
    # do titular (art. 18), que não podem depender de concordar com a versão nova.
    FREE_ROUTES = [
        "terms_accept",
        "logout",
        "core:terms",
        "core:terms_version",
        "core:privacy",
        "core:privacy_version",
        "my_data",
        "my_data_export",
        "my_data_delete",
        "revoke_consent",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Roda depois de a URL ser resolvida: a rota já tem nome e a view ainda não executou
        if not request.user.is_authenticated:
            return None
        if request.resolver_match.view_name in self.FREE_ROUTES:
            return None
        if has_current_consent(request.user):
            return None
        return redirect("terms_accept")
