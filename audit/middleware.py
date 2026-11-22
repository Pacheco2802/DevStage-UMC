from contextvars import ContextVar

from core.utils import get_client_ip

# A requisição em andamento, visível só para o código que roda dentro dela (por thread ou tarefa)
_current_request = ContextVar("audit_current_request", default=None)


class AuditMiddleware:
    """Deixa a requisição corrente ao alcance dos sinais de auditoria (RN60).

    Os sinais post_save e post_delete não recebem a requisição. Guardando-a aqui, o registro de
    criação, alteração e exclusão passa a dizer também quem fez a ação, de onde e em qual tela."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            # Sem isto, a requisição seguinte da mesma thread herdaria o usuário desta
            _current_request.reset(token)


def current_actor():
    """Usuário, caminho e IP da requisição em andamento. Fora de uma requisição (comando de
    terminal, migração) ou em ação de visitante, o usuário é None."""
    request = _current_request.get()
    if request is None:
        return {"user": None, "path": "", "ip": None}
    user = getattr(request, "user", None)
    return {
        "user": user if user is not None and user.is_authenticated else None,
        "path": request.path[:500],
        "ip": get_client_ip(request),
    }
