"""
Testes unitários do controle de acesso: os três decoradores de perfil (core.decorators), o
middleware que exige o aceite dos termos (RN66) e a leitura do IP atrás de proxy (RN59).

Nada aqui toca o banco: os usuários são objetos em memória e as requisições vêm do
RequestFactory, que monta a requisição sem passar pelo servidor.
"""
from unittest.mock import patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import resolve, reverse

from accounts.middleware import TermsConsentMiddleware
from accounts.models import CompanyProfile, User
from core.decorators import approved_company_required, company_required, student_required
from core.utils import get_client_ip, get_user_agent


def _view(request):
    return HttpResponse("conteúdo protegido")


def _request(user, path="/challenges/novo/", **extra):
    request = RequestFactory().get(path, **extra)
    request.user = user
    request._messages = CookieStorage(request)  # as mensagens ficam na requisição, sem sessão
    return request


def _empresa(approved):
    user = User(username="empresa", role=User.Role.COMPANY)
    user.company_profile = CompanyProfile(company_name="Acme", approved=approved)
    return user


def _mensagens(request):
    return [str(mensagem) for mensagem in get_messages(request)]


ESTUDANTE = User(username="aluno", role=User.Role.STUDENT)


# ---------- Decoradores de perfil (RNF03: a regra vale no servidor) ----------

@pytest.mark.parametrize("decorador, user", [
    [student_required, ESTUDANTE],
    [company_required, _empresa(approved=False)],
    [approved_company_required, _empresa(approved=True)],
])
def test_decorador_comOPerfilCerto_deveExecutarAView(decorador, user):
    response = decorador(_view)(_request(user))

    assert response.status_code == 200
    assert response.content.decode() == "conteúdo protegido"


@pytest.mark.parametrize("decorador, user, mensagem", [
    [student_required, _empresa(approved=True), "Apenas estudantes podem acessar esta página."],
    [company_required, ESTUDANTE, "Apenas empresas podem acessar esta página."],
    [approved_company_required, ESTUDANTE, "Apenas empresas podem acessar esta página."],
    [approved_company_required, _empresa(approved=False), "Sua empresa ainda não foi aprovada por um administrador."],
])
def test_decorador_comOPerfilErrado_deveRedirecionarComOMotivo(decorador, user, mensagem):
    request = _request(user)

    response = decorador(_view)(request)

    assert response.status_code == 302
    assert response.url == reverse("challenges:list")
    assert _mensagens(request) == [mensagem]


@pytest.mark.parametrize("decorador", [student_required, company_required, approved_company_required])
def test_decorador_semSessao_deveMandarParaOLogin(decorador):
    response = decorador(_view)(_request(AnonymousUser()))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


# ---------- TermsConsentMiddleware (RN66) ----------

def _process_view(user, path, aceite_em_dia):
    request = _request(user, path)
    request.resolver_match = resolve(path)
    with patch("accounts.middleware.has_current_consent", return_value=aceite_em_dia) as consulta:
        response = TermsConsentMiddleware(_view).process_view(request, _view, [], {})
    return response, consulta


def test_termos_usuarioSemAceiteDaVersaoVigente_deveIrParaATelaDeAceite():
    response, _ = _process_view(ESTUDANTE, "/challenges/", aceite_em_dia=False)

    assert response.status_code == 302
    assert response.url == reverse("terms_accept")


def test_termos_usuarioComAceiteEmDia_deveSeguirNormalmente():
    response, _ = _process_view(ESTUDANTE, "/challenges/", aceite_em_dia=True)

    assert response is None  # None = o Django segue para a view


@pytest.mark.parametrize("path", [
    "/accounts/termos/aceitar/", "/accounts/logout/", "/termos/", "/termos/1.0/", "/privacidade/",
    "/privacidade/1.1/", "/accounts/meus-dados/", "/accounts/meus-dados/exportar/",
    "/accounts/meus-dados/excluir/", "/accounts/meus-dados/revogar-consentimento/",
])
def test_termos_rotasDosDireitosDoTitular_ficamLiberadasSemOAceite(path):
    response, consulta = _process_view(ESTUDANTE, path, aceite_em_dia=False)

    assert response is None
    consulta.assert_not_called()  # rota liberada nem chega a consultar o aceite


def test_termos_visitante_naoEBarradoNasPaginasPublicas():
    response, consulta = _process_view(AnonymousUser(), "/portfolio/ranking/", aceite_em_dia=False)

    assert response is None
    consulta.assert_not_called()


def test_termos_middleware_repassaARequisicao():
    request = _request(ESTUDANTE)

    assert TermsConsentMiddleware(_view)(request).status_code == 200


# ---------- IP e navegador da requisição (RN59) ----------

def test_ip_semProxy_deveVirDoRemoteAddr():
    assert get_client_ip(RequestFactory().get("/", REMOTE_ADDR="10.0.0.7")) == "10.0.0.7"


def test_ip_atrasDeProxy_deveSerOPrimeiroEnderecoDoXForwardedFor():
    request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1")

    assert get_client_ip(request) == "203.0.113.9"


def test_ipENavegador_semRequisicao_devemSerVazios():
    assert get_client_ip(None) is None
    assert get_user_agent(None) == ""


def test_navegador_muitoLongo_deveSerCortadoEm300Caracteres():
    request = RequestFactory().get("/", HTTP_USER_AGENT="x" * 500)

    assert len(get_user_agent(request)) == 300
