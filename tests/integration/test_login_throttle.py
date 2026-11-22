"""
Testes de integração do limite de tentativas de login (proteção contra força bruta).
"""
from datetime import timedelta

import pytest
from django.contrib.auth import authenticate
from django.urls import reverse
from django.utils import timezone

from accounts import throttle
from accounts.models import LoginAttempt, User
from audit.models import AuditLog

SENHA = "senha-teste-123"
BLOQUEIO = "Muitas tentativas de login."


def _entrar(client, username="aluno", password=SENHA, **extra):
    return client.post(reverse("login"), {"username": username, "password": password}, **extra)


def _errar(client, vezes, username="aluno", **extra):
    for _ in range(vezes):
        _entrar(client, username, "senha-errada", **extra)


def _logado(client):
    return "_auth_user_id" in client.session


@pytest.mark.django_db
def test_login_comQuatroFalhas_aindaPermiteEntrar(client, estudante):
    _errar(client, 4)

    _entrar(client)

    assert _logado(client)


@pytest.mark.django_db
def test_login_naQuintaFalha_bloqueiaMesmoComASenhaCerta(client, estudante):
    _errar(client, 5)

    response = _entrar(client)

    assert not _logado(client)
    assert BLOQUEIO in response.content.decode()
    assert "Tente novamente em 15 minutos." in response.content.decode()


@pytest.mark.django_db
def test_login_bloqueado_naoConfereASenhaNemGravaNovaFalha(client, estudante, monkeypatch):
    _errar(client, 5)
    conferencias = []
    monkeypatch.setattr(User, "check_password", lambda self, senha: conferencias.append(senha) or True)

    _entrar(client)
    _entrar(client, password="outra-tentativa")

    assert conferencias == []  # o hash lento da senha não chega a ser calculado
    assert LoginAttempt.objects.count() == 5  # tentar durante o bloqueio não o prolonga


@pytest.mark.django_db
def test_login_depoisDaJanela_voltaAFuncionar(client, estudante):
    _errar(client, 5)
    LoginAttempt.objects.update(failed_at=timezone.now() - throttle.JANELA - timedelta(seconds=1))

    _entrar(client)

    assert _logado(client)


@pytest.mark.django_db
def test_login_bloqueioInformaQuantosMinutosFaltam(client, estudante):
    _errar(client, 5)
    LoginAttempt.objects.update(failed_at=timezone.now() - timedelta(minutes=12, seconds=30))

    response = _entrar(client)

    assert "Tente novamente em 3 minutos." in response.content.decode()


@pytest.mark.django_db
def test_login_correto_zeraAContagemDeFalhas(client, estudante):
    _errar(client, 4)
    _entrar(client)
    client.post(reverse("logout"))

    _errar(client, 4)
    _entrar(client)

    assert _logado(client)  # sem zerar, a oitava falha já teria bloqueado
    assert not LoginAttempt.objects.exists()


@pytest.mark.django_db
def test_login_bloqueioDeUmUsuario_naoAfetaOutro(client, estudante, empresa):
    _errar(client, 5, username="aluno")

    _entrar(client, username="empresa")

    assert _logado(client)


@pytest.mark.django_db
def test_login_nomeDeUsuarioNaoDiferenciaMaiusculasNoLimite(client, estudante):
    for variacao in ["aluno", "ALUNO", " Aluno ", "aLuNo", "aluno"]:
        _entrar(client, variacao, "senha-errada")

    assert throttle.minutos_de_bloqueio("aluno", None) == 15


@pytest.mark.django_db
def test_login_usuarioInexistente_tambemEBloqueado_semRevelarQueNaoExiste(client):
    _errar(client, 5, username="nao-existe")

    response = _entrar(client, username="nao-existe", password="qualquer")

    assert BLOQUEIO in response.content.decode()


@pytest.mark.django_db
def test_login_muitasFalhasDoMesmoIp_bloqueiaOIpParaQualquerUsuario(client, estudante):
    # 20 falhas do mesmo endereço, espalhadas por nomes diferentes: nenhum nome chega a 5
    for numero in range(20):
        _entrar(client, f"alvo{numero}", "senha-errada", REMOTE_ADDR="203.0.113.7")

    do_mesmo_ip = _entrar(client, REMOTE_ADDR="203.0.113.7")
    assert not _logado(client)
    assert BLOQUEIO in do_mesmo_ip.content.decode()

    _entrar(client, REMOTE_ADDR="198.51.100.4")  # de outro endereço, o estudante entra normalmente
    assert _logado(client)


@pytest.mark.django_db
def test_login_oBloqueioValeTambemParaAAreaAdministrativa(client, admin_user, settings):
    # Em produção os estáticos passam pelo collectstatic; no teste, a página usa os arquivos direto
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    for _ in range(5):
        client.post("/admin/login/", {"username": admin_user.username, "password": "senha-errada"})

    client.post("/admin/login/", {"username": admin_user.username, "password": "password"})

    assert not _logado(client)


@pytest.mark.django_db
def test_login_inicioDoBloqueio_ficaNaAuditoria(client, estudante):
    _errar(client, 5, REMOTE_ADDR="203.0.113.7")

    registro = AuditLog.objects.get(target_model="LoginBlocked")
    assert registro.target_id == "aluno"
    assert registro.ip == "203.0.113.7"
    assert registro.path == reverse("login")


@pytest.mark.django_db
def test_login_falhasAntigasSaoApagadas(client, estudante):
    _errar(client, 2)
    LoginAttempt.objects.update(failed_at=timezone.now() - timedelta(days=2))

    _errar(client, 1)

    assert LoginAttempt.objects.count() == 1


@pytest.mark.django_db
def test_autenticacaoSemRequisicao_tambemRespeitaOLimite(estudante):
    # authenticate() chamado fora de uma tela, sem requisição: vale a regra por nome de usuário
    for _ in range(5):
        assert authenticate(username="aluno", password="senha-errada") is None

    assert authenticate(username="aluno", password=SENHA) is None


@pytest.mark.django_db
def test_login_telaDeLoginContinuaAbrindoDuranteOBloqueio(client, estudante):
    _errar(client, 5)

    assert client.get(reverse("login")).status_code == 200
