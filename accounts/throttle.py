"""Limite de tentativas de login, contra adivinhação de senha por força bruta.

Cada tentativa que falha é gravada. Depois de MAX_FALHAS_POR_USUARIO falhas para o mesmo nome
de usuário, ou de MAX_FALHAS_POR_IP vindas do mesmo endereço, dentro da JANELA, novas tentativas
são recusadas sem nem conferir a senha, até as falhas antigas saírem da janela.

Recusar antes de conferir a senha também poupa o servidor: o hash PBKDF2 é lento de propósito,
e uma enxurrada de tentativas ocuparia todos os processos da aplicação.
"""
import math
from datetime import timedelta

from django.utils import timezone

from audit.models import AuditLog

from .models import LoginAttempt

MAX_FALHAS_POR_USUARIO = 5
MAX_FALHAS_POR_IP = 20
JANELA = timedelta(minutes=15)
GUARDAR_POR = timedelta(days=1)


def normalizar(username):
    return (username or "").strip().lower()[:150]


def _falhas_recentes(**filtro):
    return LoginAttempt.objects.filter(failed_at__gt=timezone.now() - JANELA, **filtro).order_by("failed_at")


def minutos_de_bloqueio(username, ip):
    """Quantos minutos faltam para o login ser liberado, ou 0 se não há bloqueio."""
    username = normalizar(username)
    esperas = []
    for filtro, limite in [[{"username": username}, MAX_FALHAS_POR_USUARIO], [{"ip": ip}, MAX_FALHAS_POR_IP]]:
        if not all(filtro.values()):
            continue  # sem nome de usuário ou sem IP não há o que contar nessa regra
        falhas = list(_falhas_recentes(**filtro).values_list("failed_at", flat=True))
        if len(falhas) >= limite:
            # libera quando a falha mais antiga das que contam para o limite sair da janela
            libera_em = falhas[-limite] + JANELA
            esperas.append((libera_em - timezone.now()).total_seconds())
    return max(1, math.ceil(max(esperas) / 60)) if esperas else 0


def registrar_falha(username, ip, path=""):
    username = normalizar(username)
    if not username:
        return
    LoginAttempt.objects.create(username=username, ip=ip)
    LoginAttempt.objects.filter(failed_at__lt=timezone.now() - GUARDAR_POR).delete()
    if _falhas_recentes(username=username).count() == MAX_FALHAS_POR_USUARIO:
        # O início do bloqueio fica na trilha de auditoria, para o administrador acompanhar
        AuditLog.objects.create(
            action=AuditLog.Action.ACCESS, target_model="LoginBlocked", target_id=username[:50], path=path[:500], ip=ip,
        )


def limpar_falhas(username):
    """Login correto zera a contagem daquele usuário."""
    LoginAttempt.objects.filter(username=normalizar(username)).delete()
