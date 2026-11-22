from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from core.utils import get_client_ip

from . import throttle


class ThrottledModelBackend(ModelBackend):
    """Autenticação padrão do Django com limite de tentativas.

    Fica no backend, e não só na tela de login, para valer em qualquer porta de entrada,
    inclusive no login da área administrativa."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return super().authenticate(request, username=username, password=password, **kwargs)

        ip = get_client_ip(request)
        if throttle.minutos_de_bloqueio(username, ip):
            # PermissionDenied encerra a autenticação aqui: a senha nem chega a ser conferida
            raise PermissionDenied

        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is None:
            throttle.registrar_falha(username, ip, path=request.path if request else "")
        else:
            throttle.limpar_falhas(username)
        return user
