"""
Testes unitários do raio-X da entrega: os pontos de atenção (build_alerts), a comparação de
repositórios, a classe RepoSnapshot e o middleware de auditoria.

Nada aqui toca o banco nem a rede: os objetos são montados em memória, sem .save().
"""
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from accounts.models import CompanyProfile, ConsentLog, StudentProfile, TermsVersion, User
from audit.middleware import AuditMiddleware, current_actor
from audit.models import AuditLog
from challenges.models import Challenge, Evaluation, RepoSnapshot, Submission
from challenges.services import _repo_facts, _repo_key, build_alerts
from core.management.commands.seed_demo import gerar_username
from dashboard.services import perfil_do_dashboard
from portfolio.forms import StudentProfileForm

PUBLICADO_EM = datetime(2026, 11, 1, 12, 0, tzinfo=dt_timezone.utc)
SHA = "a" * 40


def _snapshot(report=None, repo_url="https://github.com/aluno/api", commit_sha=SHA, **campos):
    desafio = Challenge(title="API de pedidos", created_at=PUBLICADO_EM)
    submissao = Submission(
        challenge=desafio, student=User(username="aluno"), repo_url=repo_url,
        submitted_at=PUBLICADO_EM + timedelta(days=2),
    )
    return RepoSnapshot(submission=submissao, commit_sha=commit_sha, report=report or {}, **campos)


def _codigos(report):
    return [alerta["code"] for alerta in build_alerts(_snapshot(report))]


# ---------- build_alerts: indícios para a empresa conferir ----------

def test_alertas_entregaSemNadaFora_naoGeraNenhum():
    report = {"repo": {"fork": False, "created_at": "2026-11-02T10:00:00Z"}, "history": {"count": 12, "authors": 1}}

    assert build_alerts(_snapshot(report)) == []


def test_alertas_relatorioVazio_naoQuebra():
    assert build_alerts(_snapshot({})) == []


@pytest.mark.parametrize("issue", ["env_file", "deps_committed", "private_key"])
def test_alertas_problemaNosArquivos_viraAlertaComTexto(issue):
    alertas = build_alerts(_snapshot({"issues": [issue]}))

    assert [alerta["code"] for alerta in alertas] == [issue]
    assert len(alertas[0]["text"]) > 20


def test_alertas_fork_deveCitarORepositorioOriginal():
    alertas = build_alerts(_snapshot({"repo": {"fork": True, "parent": "empresa/modelo"}}))

    assert alertas == [{"code": "fork", "text": "O repositório é um fork de empresa/modelo."}]


def test_alertas_forkSemOrigemConhecida_naoInventaONome():
    alertas = build_alerts(_snapshot({"repo": {"fork": True, "parent": ""}}))

    assert alertas[0]["text"] == "O repositório é um fork."


@pytest.mark.parametrize("criado_em, alerta", [
    ["2026-10-31T23:59:59Z", True],   # criado antes de o desafio ser publicado
    ["2026-11-01T12:00:00Z", False],  # no mesmo instante da publicação
    ["2026-11-03T08:00:00Z", False],  # depois
    ["", False],                      # o GitHub não informou a data
])
def test_alertas_repositorioMaisAntigoQueODesafio(criado_em, alerta):
    codigos = _codigos({"repo": {"created_at": criado_em}})

    assert ("repo_older_than_challenge" in codigos) is alerta


@pytest.mark.parametrize("commits, alerta", [[1, True], [2, False], [0, False]])
def test_alertas_commitUnico(commits, alerta):
    assert ("single_commit" in _codigos({"history": {"count": commits}})) is alerta


@pytest.mark.parametrize("autores, alerta", [[1, False], [2, True], [5, True]])
def test_alertas_maisDeUmAutor(autores, alerta):
    alertas = build_alerts(_snapshot({"history": {"authors": autores, "count": 9}}))

    assert bool(alertas) is alerta
    if alerta:
        assert alertas[0]["text"] == f"Os commits têm {autores} autores diferentes."


def test_alertas_variosIndicios_aparecemTodos():
    report = {
        "issues": ["env_file"], "repo": {"fork": True, "parent": "a/b", "created_at": "2026-01-01T00:00:00Z"},
        "history": {"count": 1, "authors": 1},
    }

    assert _codigos(report) == ["env_file", "fork", "repo_older_than_challenge", "single_commit"]


# ---------- Comparação de repositórios (mesma entrega por outro estudante) ----------

@pytest.mark.parametrize("url", [
    "https://github.com/Aluno/API", "https://github.com/aluno/api.git", "https://github.com/aluno/api/",
    "http://github.com/ALUNO/api",
])
def test_repoKey_variacoesDaMesmaUrl_saoOMesmoRepositorio(url):
    assert _repo_key(url) == _repo_key("https://github.com/aluno/api")


def test_repoKey_repositoriosDiferentes_naoSeConfundem():
    assert _repo_key("https://github.com/aluno/api") != _repo_key("https://github.com/aluno/api-v2")


def test_repoKey_urlForaDoPadrao_voltaAPropriaUrl():
    assert _repo_key("https://gitlab.com/aluno/api") == "https://gitlab.com/aluno/api"


@pytest.mark.parametrize("resposta", [None, "texto", 42, []])
def test_repoFacts_semRespostaDoGithub_devolveVazio(resposta):
    assert _repo_facts(resposta) == {}


def test_repoFacts_guardaSoOQueORaioXUsa():
    resposta = {
        "fork": True, "parent": {"full_name": "empresa/modelo"}, "created_at": "2026-11-02T10:00:00Z",
        "owner": {"login": "aluno", "email": "aluno@email.com"}, "stargazers_count": 3,
    }

    assert _repo_facts(resposta) == {"fork": True, "parent": "empresa/modelo", "created_at": "2026-11-02T10:00:00Z"}


# ---------- Classe RepoSnapshot ----------

def test_snapshot_commitUrl_apontaParaOCodigoNoCommitRegistrado():
    assert _snapshot().commit_url == f"https://github.com/aluno/api/tree/{SHA}"


def test_snapshot_semCommitRegistrado_naoTemLink():
    assert _snapshot(commit_sha="").commit_url == ""


@pytest.mark.parametrize("atraso, report, tardio", [
    [timedelta(seconds=5), {}, False],                              # registrado junto com a entrega
    [timedelta(minutes=9), {}, False],
    [timedelta(minutes=11), {}, True],                              # entrega anterior ao recurso
    [timedelta(seconds=5), {"commit_from_analysis": True}, True],   # GitHub fora do ar na entrega
])
def test_snapshot_registeredLate(atraso, report, tardio):
    snapshot = _snapshot(report)
    snapshot.created_at = snapshot.submission.submitted_at + atraso

    assert snapshot.registered_late is tardio


def test_snapshot_practices_marcaOQueORepositorioTem():
    snapshot = _snapshot({"practices": ["docker", "ci"]})

    assert snapshot.practices == [
        [".gitignore", False], ["Licença", False], ["Docker", True], ["Pipeline de CI", True], [".env de exemplo", False],
    ]


def test_snapshotNovo_comecaComAnalisePendente():
    assert RepoSnapshot().status == RepoSnapshot.Status.PENDING


# ---------- Representação em texto dos modelos (aparece na área administrativa) ----------

def test_str_dosModelos():
    aluno = User(username="aluno")
    desafio = Challenge(title="API de pedidos")
    submissao = Submission(challenge=desafio, student=aluno)

    assert str(submissao) == "aluno → API de pedidos"
    assert str(Evaluation(submission=submissao, score=85)) == "aluno → API de pedidos - nota 85"
    assert str(RepoSnapshot(submission=submissao)) == "Raio-X de aluno → API de pedidos"
    assert str(CompanyProfile(company_name="Acme Tech")) == "Acme Tech"
    assert str(StudentProfile(user=aluno)) == "Perfil de aluno"
    assert str(TermsVersion(version="1.2")) == "Termos v1.2"
    assert str(ConsentLog(user=aluno, terms_version="1.2")) == "aluno - termos v1.2"


def test_str_doRegistroDeAuditoria_semUsuario_mostraAnonimo():
    registro = AuditLog(action="CREATE", target_model="Challenge", target_id="7", timestamp=PUBLICADO_EM)

    assert str(registro) == "[2026-11-01 12:00] anônimo · CREATE · Challenge#7"


# ---------- AuditMiddleware (RN60) ----------

def test_auditoria_duranteARequisicao_oAutorEOUsuarioAutenticado():
    usuario = User(username="empresa")
    visto = {}

    def view(request):
        visto.update(current_actor())
        return HttpResponse()

    request = RequestFactory().post("/challenges/novo/", REMOTE_ADDR="10.0.0.5")
    request.user = usuario
    AuditMiddleware(view)(request)

    assert visto == {"user": usuario, "path": "/challenges/novo/", "ip": "10.0.0.5"}


def test_auditoria_visitante_naoEAutorMasCaminhoEIpFicam():
    visto = {}

    def view(request):
        visto.update(current_actor())
        return HttpResponse()

    request = RequestFactory().post("/accounts/signup/estudante/", REMOTE_ADDR="10.0.0.7")
    request.user = AnonymousUser()
    AuditMiddleware(view)(request)

    assert visto == {"user": None, "path": "/accounts/signup/estudante/", "ip": "10.0.0.7"}


def test_auditoria_depoisDaRequisicao_oContextoVoltaAoEstadoInicial():
    request = RequestFactory().get("/")
    request.user = User(username="empresa")

    AuditMiddleware(lambda request: HttpResponse())(request)

    assert current_actor() == {"user": None, "path": "", "ip": None}


def test_auditoria_mesmoComErroNaView_oContextoELimpo():
    def view(request):
        raise RuntimeError("falha na view")

    request = RequestFactory().get("/")
    request.user = User(username="empresa")

    with pytest.raises(RuntimeError):
        AuditMiddleware(view)(request)

    assert current_actor()["user"] is None


# ---------- Funções auxiliares ----------

@pytest.mark.parametrize("nome, username", [
    ["Letícia Prado", "lprado"],
    ["André Bastos", "abastos"],
    ["Júlia de Moreira", "jdemoreira"],
])
def test_gerarUsername_inicialDoNomeMaisSobrenomeSemAcentos(nome, username):
    assert gerar_username(nome) == username


@pytest.mark.parametrize("user, perfil", [
    [User(role=User.Role.STUDENT), "STUDENT"],
    [User(role=User.Role.COMPANY), "COMPANY"],
    [User(role=User.Role.PLATFORM_ADMIN), "ADMIN"],
    [User(role=User.Role.STUDENT, is_superuser=True), "ADMIN"],  # createsuperuser cria com o papel padrão
])
def test_perfilDoDashboard(user, perfil):
    assert perfil_do_dashboard(user) == perfil


def test_formDoPerfil_soTemOsCamposQueOEstudanteEscolhe():
    assert list(StudentProfileForm().fields) == ["bio", "github_username", "portfolio_public"]
