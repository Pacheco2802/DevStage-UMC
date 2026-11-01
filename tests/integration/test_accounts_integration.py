"""
Testes de integração dos endpoints de conta: cadastro (accounts/views.py) e login/logout
(views de autenticação do Django incluídas em accounts/urls.py).

Fluxo exercitado: django.test.Client -> URLconf -> middlewares (sessão, CSRF, auth)
-> view -> form -> ORM -> PostgreSQL de teste. Nenhum mock.
"""
import uuid

import pytest
from django.test import Client

from accounts.models import CompanyProfile, User
from audit.models import AuditLog

SENHA = "Senha-Forte-2026!"


def _unico(prefixo):
    return f"{prefixo}-{uuid.uuid4().hex[:8]}"


@pytest.mark.django_db
class TestAccountEndpoints:

    @pytest.fixture(autouse=True)
    def configurar_cliente(self, client):
        self.client = client

    # ---------- GET /accounts/signup/estudante/ ----------

    def test_cadastroEstudante_get_deveRetornar200ComFormularioEAceiteLgpd(self):
        response = self.client.get("/accounts/signup/estudante/")

        assert response.status_code == 200
        body = response.content.decode()
        for campo in ["username", "email", "first_name", "password1", "password2", "accept_lgpd"]:
            assert f'name="{campo}"' in body
        assert "/privacidade/" in body

    # ---------- POST /accounts/signup/estudante/ ----------

    def test_cadastroEstudante_comDadosValidos_deveRetornar302PersistirELogarComoEstudante(self):
        dados = self._build_cadastro_estudante()

        response = self.client.post("/accounts/signup/estudante/", dados)

        assert response.status_code == 302
        assert response.headers["Location"] == "/challenges/"
        user = User.objects.get(username=dados["username"])
        assert user.role == User.Role.STUDENT
        assert user.email == dados["email"]
        assert user.check_password(SENHA)
        assert self.client.session["_auth_user_id"] == str(user.pk)

    def test_cadastroEstudante_comUsernameDuplicado_deveRetornar200ComErroENaoDuplicar(self):
        dados = self._build_cadastro_estudante()
        self._criar_estudante(dados)

        response = Client().post("/accounts/signup/estudante/", {**dados, "email": "outro@teste.com"})

        assert response.status_code == 200
        assert "username" in response.context["form"].errors
        assert User.objects.filter(username=dados["username"]).count() == 1

    def test_cadastroEstudante_semAceiteLgpd_deveRetornar200ComErroENaoPersistir(self):
        dados = self._build_cadastro_estudante()
        del dados["accept_lgpd"]

        response = self.client.post("/accounts/signup/estudante/", dados)

        assert response.status_code == 200
        assert "accept_lgpd" in response.context["form"].errors
        assert not User.objects.filter(username=dados["username"]).exists()

    def test_cadastroEstudante_comSenhasDiferentes_deveRetornar200ComErroENaoPersistir(self):
        dados = {**self._build_cadastro_estudante(), "password2": "Outra-Senha-2026!"}

        response = self.client.post("/accounts/signup/estudante/", dados)

        assert response.status_code == 200
        assert "password2" in response.context["form"].errors
        assert not User.objects.filter(username=dados["username"]).exists()

    # ---------- GET /accounts/signup/empresa/ ----------

    def test_cadastroEmpresa_get_deveRetornar200ComCampoNomeDaEmpresa(self):
        response = self.client.get("/accounts/signup/empresa/")

        assert response.status_code == 200
        assert 'name="company_name"' in response.content.decode()

    # ---------- POST /accounts/signup/empresa/ ----------

    def test_cadastroEmpresa_comDadosValidos_deveCriarUsuarioEPerfilAguardandoAprovacao(self):
        dados = self._build_cadastro_empresa()

        response = self.client.post("/accounts/signup/empresa/", dados)

        assert response.status_code == 302
        assert response.headers["Location"] == "/challenges/"
        user = User.objects.get(username=dados["username"])
        assert user.role == User.Role.COMPANY
        perfil = CompanyProfile.objects.get(user=user)
        assert perfil.company_name == dados["company_name"]
        assert perfil.approved is False

    def test_cadastroEmpresa_semTokenCsrf_deveRetornar403ENaoPersistir(self):
        cliente_com_csrf = Client(enforce_csrf_checks=True)
        dados = self._build_cadastro_empresa()

        response = cliente_com_csrf.post("/accounts/signup/empresa/", dados)

        assert response.status_code == 403
        assert "CSRF" in response.content.decode()
        assert not User.objects.filter(username=dados["username"]).exists()
        assert CompanyProfile.objects.count() == 0

    # ---------- GET/POST /accounts/login/ ----------

    def test_login_get_deveRetornar200ComFormulario(self):
        response = self.client.get("/accounts/login/")

        assert response.status_code == 200
        body = response.content.decode()
        assert 'name="username"' in body
        assert 'name="password"' in body

    def test_login_comCredenciaisValidas_deveRetornar302EGravarAuditoria(self):
        dados = self._build_cadastro_estudante()
        user = self._criar_estudante(dados)
        logins_antes = AuditLog.objects.filter(user=user, action=AuditLog.Action.LOGIN).count()

        response = self.client.post("/accounts/login/", {"username": dados["username"], "password": SENHA})

        assert response.status_code == 302
        assert response.headers["Location"] == "/challenges/"
        assert self.client.session["_auth_user_id"] == str(user.pk)
        assert AuditLog.objects.filter(user=user, action=AuditLog.Action.LOGIN).count() == logins_antes + 1

    def test_login_comSenhaErrada_deveRetornar200ComErroESemSessao(self):
        dados = self._build_cadastro_estudante()
        self._criar_estudante(dados)

        response = self.client.post("/accounts/login/", {"username": dados["username"], "password": "senha-errada"})

        assert response.status_code == 200
        assert response.context["form"].non_field_errors()
        assert "_auth_user_id" not in self.client.session

    # ---------- /accounts/logout/ ----------

    def test_logout_comGet_deveRetornar405ComHeaderAllow(self):
        response = self.client.get("/accounts/logout/")

        assert response.status_code == 405
        assert "POST" in response.headers["Allow"]

    def test_logout_comPost_deveRetornar302EEncerrarSessao(self):
        user = self._criar_estudante(self._build_cadastro_estudante())
        self.client.force_login(user)

        response = self.client.post("/accounts/logout/")

        assert response.status_code == 302
        assert response.headers["Location"] == "/accounts/login/"
        assert "_auth_user_id" not in self.client.session
        assert AuditLog.objects.filter(user=user, action=AuditLog.Action.LOGOUT).exists()

    # ---------- Helpers ----------

    def _build_cadastro_estudante(self):
        username = _unico("aluno")
        return {
            "username": username,
            "email": f"{username}@teste.com",
            "first_name": "Aluno",
            "password1": SENHA,
            "password2": SENHA,
            "accept_lgpd": "on",
        }

    def _build_cadastro_empresa(self):
        username = _unico("empresa")
        return {
            "username": username,
            "email": f"{username}@teste.com",
            "company_name": _unico("Empresa"),
            "password1": SENHA,
            "password2": SENHA,
            "accept_lgpd": "on",
        }

    def _criar_estudante(self, dados):
        """Cria o estudante pelo endpoint real de cadastro (num cliente separado) e devolve o User."""
        response = Client().post("/accounts/signup/estudante/", dados)
        assert response.status_code == 302
        return User.objects.get(username=dados["username"])
