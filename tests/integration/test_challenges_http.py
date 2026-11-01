"""
Testes de integração dos endpoints de desafios (challenges/views.py) com HTTP REAL.

Fluxo exercitado em cada teste:
requests -> HTTP real (live_server, porta aleatória) -> middlewares (sessão, CSRF, auth)
-> view -> form -> ORM -> PostgreSQL de teste (criado e destruído pelo pytest-django)

Único mock: a chamada à API do GitHub (serviço externo), trocada via monkeypatch.
"""
import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
import requests
from django.utils import timezone

from accounts.models import CompanyProfile
from challenges.models import Challenge, Submission
from integrations.github_client import GitHubValidationResult

SENHA = "Senha-Forte-2026!"
REPO_URL = "https://github.com/aluno/api-pedidos"


def _unico(prefixo):
    # Dados únicos por execução: nenhum teste depende de outro nem de dado manual
    return f"{prefixo}-{uuid.uuid4().hex[:8]}"


@pytest.mark.django_db(transaction=True)
class TestChallengeEndpointsHttp:

    @pytest.fixture(autouse=True)
    def configurar_cliente(self, live_server, monkeypatch):
        self.base_url = live_server.url
        # O servidor roda numa thread do mesmo processo, então o monkeypatch vale para ele
        self.mock_repo_exists = MagicMock(return_value=GitHubValidationResult(True))
        monkeypatch.setattr("challenges.forms.repo_exists", self.mock_repo_exists)

    # ---------- GET /challenges/ ----------

    def test_listar_comDesafioAbertoERascunho_deveRetornar200SoComDesafioAberto(self):
        sessao_empresa, nome_empresa = self._nova_sessao_empresa()
        titulo_aberto = _unico("Desafio aberto")
        titulo_rascunho = _unico("Desafio rascunho")
        self._criar_desafio(sessao_empresa, titulo_aberto)
        self._criar_desafio(sessao_empresa, titulo_rascunho, status="DRAFT")
        sessao_aluno = self._nova_sessao_estudante()

        response = sessao_aluno.get(self._url("/challenges/"))

        assert response.status_code == 200
        assert titulo_aberto in response.text
        assert nome_empresa in response.text
        assert titulo_rascunho not in response.text

    # ---------- GET /challenges/<pk>/ ----------

    def test_detalhar_comIdExistente_deveRetornar200ComTodosOsCampos(self):
        sessao_empresa, nome_empresa = self._nova_sessao_empresa()
        titulo = _unico("API de pedidos")
        pk = self._criar_desafio(sessao_empresa, titulo)
        sessao_aluno = self._nova_sessao_estudante()

        response = sessao_aluno.get(self._url(f"/challenges/{pk}/"))

        assert response.status_code == 200
        assert titulo in response.text
        assert nome_empresa in response.text
        assert "Construa uma API REST de pedidos." in response.text
        assert "ABERTO" in response.text

    def test_detalhar_comIdInexistente_deveRetornar404ComMensagem(self):
        sessao_aluno = self._nova_sessao_estudante()

        response = sessao_aluno.get(self._url("/challenges/999999/"))

        assert response.status_code == 404
        assert "Not Found" in response.text

    # ---------- POST /challenges/<pk>/ (submissão) ----------

    def test_submeter_comDadosValidos_deveRetornar302EPersistirSubmissao(self):
        sessao_empresa, _ = self._nova_sessao_empresa()
        pk = self._criar_desafio(sessao_empresa, _unico("Desafio"))
        sessao_aluno = self._nova_sessao_estudante()

        response = self._post(sessao_aluno, f"/challenges/{pk}/", self._build_submissao_request())

        assert response.status_code == 302
        assert response.headers["Location"] == f"/challenges/{pk}/"
        submissao = Submission.objects.get(challenge_id=pk)
        assert submissao.repo_url == REPO_URL
        assert submissao.description == "Usei Django e PostgreSQL."
        self.mock_repo_exists.assert_called_once_with(REPO_URL)

    def test_submeter_emDesafioInexistente_deveRetornar404ENaoPersistir(self):
        sessao_aluno = self._nova_sessao_estudante()

        response = self._post(sessao_aluno, "/challenges/999999/", self._build_submissao_request())

        assert response.status_code == 404
        assert "Not Found" in response.text
        assert Submission.objects.count() == 0

    def test_submeter_pelaSegundaVez_deveRedirecionarComMensagemENaoDuplicar(self):
        sessao_empresa, _ = self._nova_sessao_empresa()
        pk = self._criar_desafio(sessao_empresa, _unico("Desafio"))
        sessao_aluno = self._nova_sessao_estudante()
        self._post(sessao_aluno, f"/challenges/{pk}/", self._build_submissao_request())

        response = self._post(sessao_aluno, f"/challenges/{pk}/", self._build_submissao_request())

        assert response.status_code == 302
        pagina = sessao_aluno.get(self._url(response.headers["Location"]))
        assert "Você já enviou uma submissão para este desafio." in pagina.text
        assert Submission.objects.filter(challenge_id=pk).count() == 1

    def test_submeter_comRepositorioInexistenteNoGithub_deveRetornar200ComErroENaoPersistir(self):
        sessao_empresa, _ = self._nova_sessao_empresa()
        pk = self._criar_desafio(sessao_empresa, _unico("Desafio"))
        sessao_aluno = self._nova_sessao_estudante()
        self.mock_repo_exists.return_value = GitHubValidationResult(False, "Repositório não encontrado no GitHub.")

        response = self._post(sessao_aluno, f"/challenges/{pk}/", self._build_submissao_request())

        assert response.status_code == 200
        assert "Repositório não encontrado no GitHub." in response.text
        assert Submission.objects.count() == 0

    # ---------- GET /challenges/novo/ (segurança: anônimo / sem permissão / com permissão) ----------

    def test_novoDesafio_semLogin_deveRetornar302ParaLogin(self):
        sessao_anonima = requests.Session()

        response = sessao_anonima.get(self._url("/challenges/novo/"), allow_redirects=False)

        assert response.status_code == 302
        assert response.headers["Location"] == "/accounts/login/?next=/challenges/novo/"

    def test_novoDesafio_comoEstudante_deveNegarAcessoComMensagem(self):
        sessao_aluno = self._nova_sessao_estudante()

        response = sessao_aluno.get(self._url("/challenges/novo/"), allow_redirects=False)

        assert response.status_code == 302
        assert response.headers["Location"] == "/challenges/"
        pagina = sessao_aluno.get(self._url(response.headers["Location"]))
        assert "Apenas empresas podem acessar esta página." in pagina.text

    def test_novoDesafio_comoEmpresaAprovada_deveRetornar200ComFormulario(self):
        sessao_empresa, _ = self._nova_sessao_empresa()

        response = sessao_empresa.get(self._url("/challenges/novo/"), allow_redirects=False)

        assert response.status_code == 200
        for campo in ["title", "description", "deadline", "status"]:
            assert f'name="{campo}"' in response.text

    def test_novoDesafio_comoEmpresaNaoAprovada_deveNegarAcessoComMensagem(self):
        sessao_empresa, _ = self._nova_sessao_empresa(aprovada=False)

        response = sessao_empresa.get(self._url("/challenges/novo/"), allow_redirects=False)

        assert response.status_code == 302
        pagina = sessao_empresa.get(self._url(response.headers["Location"]))
        assert "Sua empresa ainda não foi aprovada por um administrador." in pagina.text

    # ---------- POST /challenges/novo/ ----------

    def test_criarDesafio_comDadosValidos_deveRetornar302ComLocationEPersistir(self):
        sessao_empresa, nome_empresa = self._nova_sessao_empresa()
        titulo = _unico("Novo desafio")

        response = self._post(sessao_empresa, "/challenges/novo/", self._build_desafio_request(titulo))

        assert response.status_code == 302
        desafio = Challenge.objects.get(title=titulo)
        assert response.headers["Location"] == f"/challenges/{desafio.pk}/"
        assert desafio.company.company_name == nome_empresa
        assert desafio.status == Challenge.Status.OPEN

    def test_criarDesafio_semTitulo_deveRetornar200ComErroENaoPersistir(self):
        sessao_empresa, _ = self._nova_sessao_empresa()

        response = self._post(sessao_empresa, "/challenges/novo/", self._build_desafio_request(""))

        assert response.status_code == 200
        assert "Este campo é obrigatório." in response.text
        assert Challenge.objects.count() == 0

    def test_criarDesafio_semTokenCsrf_deveRetornar403ENaoPersistir(self):
        sessao_empresa, _ = self._nova_sessao_empresa()

        # POST direto, sem o csrfmiddlewaretoken que o formulário real envia
        response = sessao_empresa.post(
            self._url("/challenges/novo/"), data=self._build_desafio_request(_unico("Ataque")), allow_redirects=False
        )

        assert response.status_code == 403
        assert "CSRF" in response.text
        assert Challenge.objects.count() == 0

    # ---------- Fluxo entre recursos: empresa -> desafio -> submissão ----------

    def test_fluxo_empresaPublicaDesafioEEstudanteSubmete_deveVincularSubmissaoAoDesafioDaEmpresa(self):
        sessao_empresa, nome_empresa = self._nova_sessao_empresa()
        titulo = _unico("Desafio do fluxo")
        pk = self._criar_desafio(sessao_empresa, titulo)
        sessao_aluno = self._nova_sessao_estudante()

        lista = sessao_aluno.get(self._url("/challenges/"))
        envio = self._post(sessao_aluno, f"/challenges/{pk}/", self._build_submissao_request())
        detalhe = sessao_aluno.get(self._url(f"/challenges/{pk}/"))

        assert titulo in lista.text
        assert envio.status_code == 302
        assert "Entrega registrada com sucesso!" in detalhe.text
        assert REPO_URL in detalhe.text
        desafio = Challenge.objects.get(pk=pk)
        assert desafio.company.company_name == nome_empresa
        assert desafio.submissions.count() == 1

    # ---------- Helpers ----------

    def _url(self, path):
        return self.base_url + path

    def _post(self, sessao, path, dados):
        """POST como o navegador faz: pega o token CSRF da sessão e envia junto com o formulário."""
        sessao.get(self._url(path))
        token = sessao.cookies.get("csrftoken")
        return sessao.post(self._url(path), data={**dados, "csrfmiddlewaretoken": token}, allow_redirects=False)

    def _nova_sessao_estudante(self):
        """Cadastra um estudante pelo endpoint real; o cadastro já deixa a sessão logada."""
        sessao = requests.Session()
        username = _unico("aluno")
        response = self._post(sessao, "/accounts/signup/estudante/", {
            "username": username,
            "email": f"{username}@teste.com",
            "first_name": "Aluno",
            "password1": SENHA,
            "password2": SENHA,
            "accept_lgpd": "on",
        })
        assert response.status_code == 302
        return sessao

    def _nova_sessao_empresa(self, aprovada=True):
        """Cadastra uma empresa pelo endpoint real e, se pedido, aprova.
        A aprovação é feita pelo administrador no Django Admin; aqui ela é simulada pelo ORM."""
        sessao = requests.Session()
        username = _unico("empresa")
        nome_empresa = _unico("Empresa")
        response = self._post(sessao, "/accounts/signup/empresa/", {
            "username": username,
            "email": f"{username}@teste.com",
            "company_name": nome_empresa,
            "password1": SENHA,
            "password2": SENHA,
            "accept_lgpd": "on",
        })
        assert response.status_code == 302
        if aprovada:
            CompanyProfile.objects.filter(user__username=username).update(approved=True)
        return sessao, nome_empresa

    def _build_desafio_request(self, titulo, status="OPEN"):
        prazo = timezone.localtime() + timedelta(days=7)
        return {
            "title": titulo,
            "description": "Construa uma API REST de pedidos.",
            "deadline": prazo.strftime("%Y-%m-%dT%H:%M"),
            "status": status,
        }

    def _build_submissao_request(self):
        return {"repo_url": REPO_URL, "deploy_url": "", "description": "Usei Django e PostgreSQL."}

    def _criar_desafio(self, sessao_empresa, titulo, status="OPEN"):
        """Cria um desafio pelo endpoint real e devolve o id lido do header Location."""
        response = self._post(sessao_empresa, "/challenges/novo/", self._build_desafio_request(titulo, status))
        assert response.status_code == 302
        return int(response.headers["Location"].rstrip("/").split("/")[-1])
