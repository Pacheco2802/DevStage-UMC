"""
Raio-X da entrega: o commit é registrado na submissão e o repositório é analisado nesse commit.

Fluxo exercitado: Client -> views -> challenges.services -> PostgreSQL de teste.
O GitHub é o único ponto simulado (histórico de commits e download do código).
"""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import CompanyProfile, User
from audit.models import AuditLog
from challenges.models import Challenge, Evaluation, RepoSnapshot, Submission
from challenges.services import analyze_snapshot, duplicates_of, freeze_submission
from integrations.github_client import (
    CommitHistory,
    EmptyRepoError,
    GitHubValidationResult,
    RepoDownloadError,
    RepoFile,
)

SHA = "a" * 40
DADOS_ENTREGA = {
    "repo_url": "https://github.com/aluno/api-pedidos",
    "deploy_url": "",
    "description": "Usei Django REST e Postgres.",
}


def _historico(**extra):
    dados = {
        "head_sha": SHA, "count": 12, "capped": False,
        "first_at": "2026-11-10T09:00:00Z", "last_at": "2026-11-12T15:00:00Z",
        "active_days": 3, "authors": 1,
    }
    dados.update(extra)
    return CommitHistory(**dados)


def _arquivo(path, texto):
    dados = texto.encode()
    return RepoFile(path=path, size=len(dados), data=dados)


ARQUIVOS = [
    _arquivo("README.md", "Como rodar o projeto. " * 20),
    _arquivo("requirements.txt", "Django==5.2\npytest\n"),
    _arquivo("app/views.py", "x = 1\n" * 40),
    _arquivo("tests/test_views.py", "x = 1\n" * 10),
]


@pytest.fixture
def github(monkeypatch):
    """GitHub simulado respondendo bem; cada teste troca o que precisar."""
    chamadas = {"download": []}

    def baixar(url, ref=""):
        chamadas["download"].append(ref)
        return ref or SHA, ARQUIVOS

    monkeypatch.setattr("challenges.forms.repo_exists", lambda url: GitHubValidationResult(True, data={"fork": False}))
    monkeypatch.setattr("challenges.services.list_commits", lambda url: _historico())
    monkeypatch.setattr("challenges.services.download_repo", baixar)
    return chamadas


@pytest.fixture
def submissao(estudante, desafio_aberto):
    return Submission.objects.create(
        challenge=desafio_aberto, student=estudante,
        repo_url="https://github.com/aluno/api-pedidos", description="Minha solução",
    )


def _codigos(snapshot):
    return [alerta["code"] for alerta in snapshot.alerts]


# ---------- Na entrega: registrar o commit ----------

@pytest.mark.django_db
def test_entrega_registra_o_commit_do_momento_e_deixa_a_analise_pendente(client, estudante, desafio_aberto, github):
    client.force_login(estudante)

    client.post(reverse("challenges:detail", args=[desafio_aberto.pk]), DADOS_ENTREGA)

    snapshot = Submission.objects.get(student=estudante).snapshot
    assert snapshot.commit_sha == SHA
    assert snapshot.status == RepoSnapshot.Status.PENDING
    assert snapshot.report["history"]["count"] == 12
    assert github["download"] == []  # o código só é baixado quando a empresa abre a avaliação


@pytest.mark.django_db
def test_falha_do_github_nao_impede_a_entrega(client, estudante, desafio_aberto, github, monkeypatch):
    def sem_github(url):
        raise RepoDownloadError("GitHub fora do ar")

    monkeypatch.setattr("challenges.services.list_commits", sem_github)
    client.force_login(estudante)

    client.post(reverse("challenges:detail", args=[desafio_aberto.pk]), DADOS_ENTREGA)

    snapshot = Submission.objects.get(student=estudante).snapshot
    assert snapshot.commit_sha == ""
    assert snapshot.status == RepoSnapshot.Status.PENDING


def _repositorio_vazio(url):
    raise EmptyRepoError("GitHub respondeu 409 ao consultar os commits.")


@pytest.mark.django_db
def test_entrega_de_repositorio_vazio_e_recusada(client, estudante, desafio_aberto, github, monkeypatch):
    # Sem commit na entrega não haveria o que registrar, e o código poderia chegar depois do prazo
    monkeypatch.setattr("challenges.services.list_commits", _repositorio_vazio)
    client.force_login(estudante)

    response = client.post(reverse("challenges:detail", args=[desafio_aberto.pk]), DADOS_ENTREGA)

    assert not Submission.objects.filter(student=estudante).exists()
    assert not RepoSnapshot.objects.exists()
    assert not AuditLog.objects.filter(target_model="Submission").exists()
    assert "O repositório está vazio" in response.content.decode()


@pytest.mark.django_db
def test_depois_da_recusa_o_estudante_entrega_com_o_repositorio_preenchido(
    client, estudante, desafio_aberto, github, monkeypatch,
):
    client.force_login(estudante)
    monkeypatch.setattr("challenges.services.list_commits", _repositorio_vazio)
    client.post(reverse("challenges:detail", args=[desafio_aberto.pk]), DADOS_ENTREGA)

    monkeypatch.setattr("challenges.services.list_commits", lambda url: _historico())
    client.post(reverse("challenges:detail", args=[desafio_aberto.pk]), DADOS_ENTREGA)

    assert Submission.objects.get(student=estudante).snapshot.commit_sha == SHA


# ---------- Análise ----------

@pytest.mark.django_db
def test_analise_usa_o_commit_registrado_e_guarda_o_relatorio(submissao, github):
    snapshot = freeze_submission(submissao, {"fork": False})

    analyze_snapshot(snapshot)

    snapshot.refresh_from_db()
    assert github["download"] == [SHA]
    assert snapshot.status == RepoSnapshot.Status.READY
    assert snapshot.registered_late is False
    assert snapshot.main_language == "Python"
    assert snapshot.report["stack"] == ["Django", "pytest"]
    assert snapshot.report["readme"] == "ok"
    assert snapshot.report["test_files"] == 1
    assert snapshot.report["lines"] == 50


@pytest.mark.django_db
def test_analise_pronta_nao_baixa_o_repositorio_de_novo(submissao, github):
    snapshot = freeze_submission(submissao)
    analyze_snapshot(snapshot)

    analyze_snapshot(snapshot)

    assert len(github["download"]) == 1


@pytest.mark.django_db
def test_falha_no_download_vira_erro_com_mensagem_e_pode_ser_refeita(submissao, github, monkeypatch):
    def falha(url, ref=""):
        raise RepoDownloadError("Repositório não encontrado ou privado.")

    snapshot = freeze_submission(submissao)
    monkeypatch.setattr("challenges.services.download_repo", falha)

    analyze_snapshot(snapshot)

    snapshot.refresh_from_db()
    assert snapshot.status == RepoSnapshot.Status.ERROR
    assert snapshot.error_message == "Repositório não encontrado ou privado."

    monkeypatch.setattr("challenges.services.download_repo", lambda url, ref="": (SHA, ARQUIVOS))
    analyze_snapshot(snapshot)

    snapshot.refresh_from_db()
    assert snapshot.status == RepoSnapshot.Status.READY


@pytest.mark.django_db
def test_sem_commit_registrado_a_analise_registra_o_que_baixou(submissao, github, monkeypatch):
    def sem_github(url):
        raise RepoDownloadError("GitHub fora do ar")

    monkeypatch.setattr("challenges.services.list_commits", sem_github)
    snapshot = freeze_submission(submissao)

    analyze_snapshot(snapshot)

    snapshot.refresh_from_db()
    assert github["download"] == [""]
    assert snapshot.commit_sha == SHA
    # O GitHub não respondeu na entrega: o commit é o da primeira análise, e o painel precisa dizer isso
    assert snapshot.registered_late is True


# ---------- Alertas ----------

@pytest.mark.django_db
def test_repositorio_bem_comportado_nao_gera_alerta(submissao, github):
    snapshot = freeze_submission(submissao, {"fork": False, "created_at": timezone.now().isoformat()})

    analyze_snapshot(snapshot)

    assert snapshot.alerts == []


@pytest.mark.django_db
def test_alerta_de_fork_cita_o_repositorio_de_origem(submissao, github):
    snapshot = freeze_submission(submissao, {"fork": True, "parent": {"full_name": "outro/api-pedidos"}})

    analyze_snapshot(snapshot)

    alerta = next(a for a in snapshot.alerts if a["code"] == "fork")
    assert "outro/api-pedidos" in alerta["text"]


@pytest.mark.django_db
def test_alerta_quando_o_repositorio_e_mais_antigo_que_o_desafio(submissao, github):
    antes_do_desafio = (submissao.challenge.created_at - timedelta(days=30)).isoformat()
    snapshot = freeze_submission(submissao, {"fork": False, "created_at": antes_do_desafio})

    analyze_snapshot(snapshot)

    assert "repo_older_than_challenge" in _codigos(snapshot)


@pytest.mark.django_db
def test_alerta_de_commit_unico_e_de_mais_de_um_autor(submissao, github, monkeypatch):
    monkeypatch.setattr("challenges.services.list_commits", lambda url: _historico(count=1, active_days=1, authors=2))
    snapshot = freeze_submission(submissao)

    analyze_snapshot(snapshot)

    assert "single_commit" in _codigos(snapshot)
    assert "multiple_authors" in _codigos(snapshot)


@pytest.mark.django_db
def test_alerta_de_env_versionado(submissao, github, monkeypatch):
    arquivos = ARQUIVOS + [_arquivo(".env", "SECRET_KEY=abc")]
    monkeypatch.setattr("challenges.services.download_repo", lambda url, ref="": (SHA, arquivos))
    snapshot = freeze_submission(submissao)

    analyze_snapshot(snapshot)

    assert "env_file" in _codigos(snapshot)


@pytest.mark.django_db
def test_mesmo_repositorio_entregue_por_outro_estudante_no_mesmo_desafio(submissao, desafio_aberto, empresa):
    colega = User.objects.create_user(username="colega", password="senha-teste-123", role=User.Role.STUDENT)
    mesma = Submission.objects.create(
        challenge=desafio_aberto, student=colega,
        repo_url="https://github.com/Aluno/API-Pedidos.git", description="Cópia",
    )
    outro_desafio = Challenge.objects.create(
        company=empresa, title="Outro", description="x",
        deadline=timezone.now() + timedelta(days=7), status=Challenge.Status.OPEN,
    )
    Submission.objects.create(
        challenge=outro_desafio, student=colega,
        repo_url="https://github.com/aluno/api-pedidos", description="Outro desafio",
    )

    assert duplicates_of(submissao) == [mesma]


# ---------- Tela da empresa ----------

@pytest.mark.django_db
def test_tela_de_avaliacao_dispara_a_analise_pendente_e_para_quando_fica_pronta(client, empresa, submissao, github):
    snapshot = freeze_submission(submissao)
    client.force_login(empresa.user)
    url = reverse("challenges:evaluate", args=[submissao.pk])

    pendente = client.get(url).content.decode()
    analyze_snapshot(snapshot)
    pronta = client.get(url).content.decode()

    assert 'hx-trigger="load"' in pendente
    assert 'hx-trigger="load"' not in pronta
    assert SHA[:7] in pronta
    assert "Python" in pronta


@pytest.mark.django_db
def test_empresa_dona_gera_o_raio_x_de_entrega_antiga_sem_registro(client, empresa, submissao, github):
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:snapshot", args=[submissao.pk]))

    assert response.status_code == 200
    assert submissao.snapshot.status == RepoSnapshot.Status.READY
    assert "Django" in response.content.decode()


@pytest.mark.django_db
def test_raio_x_de_entrega_antiga_com_repositorio_vazio_mostra_o_erro_sem_quebrar(
    client, empresa, submissao, github, monkeypatch,
):
    def nada_para_baixar(url, ref=""):
        raise RepoDownloadError("GitHub respondeu 404 ao baixar o repositório.")

    monkeypatch.setattr("challenges.services.list_commits", _repositorio_vazio)
    monkeypatch.setattr("challenges.services.download_repo", nada_para_baixar)
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:snapshot", args=[submissao.pk]))

    assert response.status_code == 200
    assert submissao.snapshot.commit_sha == ""
    assert submissao.snapshot.status == RepoSnapshot.Status.ERROR


@pytest.mark.django_db
def test_raio_x_avisa_a_empresa_sobre_entrega_duplicada(client, empresa, submissao, desafio_aberto, github):
    colega = User.objects.create_user(username="colega", password="senha-teste-123", role=User.Role.STUDENT)
    Submission.objects.create(
        challenge=desafio_aberto, student=colega,
        repo_url="https://github.com/aluno/api-pedidos/", description="Cópia",
    )
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:snapshot", args=[submissao.pk]))

    assert "colega" in response.content.decode()


@pytest.mark.django_db
def test_erro_na_analise_nao_quebra_a_tela_de_avaliacao(client, empresa, submissao, github, monkeypatch):
    def falha(url, ref=""):
        raise RepoDownloadError("Repositório não encontrado ou privado.")

    monkeypatch.setattr("challenges.services.download_repo", falha)
    client.force_login(empresa.user)

    painel = client.post(reverse("challenges:snapshot", args=[submissao.pk]))
    tela = client.get(reverse("challenges:evaluate", args=[submissao.pk]))

    assert "Repositório não encontrado ou privado." in painel.content.decode()
    assert tela.status_code == 200


@pytest.mark.django_db
def test_empresa_de_outro_desafio_recebe_404(client, submissao, github):
    outra = User.objects.create_user(username="outra", password="senha-teste-123", role=User.Role.COMPANY)
    CompanyProfile.objects.create(user=outra, company_name="Outra", approved=True)
    client.force_login(outra)

    response = client.post(reverse("challenges:snapshot", args=[submissao.pk]))

    assert response.status_code == 404
    assert not RepoSnapshot.objects.exists()


@pytest.mark.django_db
def test_estudante_nao_gera_raio_x(client, estudante, submissao, github):
    client.force_login(estudante)

    client.post(reverse("challenges:snapshot", args=[submissao.pk]))

    assert not RepoSnapshot.objects.exists()


@pytest.mark.django_db
def test_raio_x_exige_post(client, empresa, submissao, github):
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:snapshot", args=[submissao.pk]))

    assert response.status_code == 405


# ---------- O que o estudante e os visitantes do portfólio veem ----------

@pytest.mark.django_db
def test_estudante_ve_o_resumo_da_propria_entrega_mas_nao_os_alertas(client, estudante, submissao, github):
    snapshot = freeze_submission(submissao, {"fork": True, "parent": {"full_name": "outro/api-pedidos"}})
    analyze_snapshot(snapshot)
    client.force_login(estudante)

    conteudo = client.get(reverse("challenges:my_submissions")).content.decode()

    assert "Python" in conteudo
    assert SHA[:7] in conteudo
    assert "outro/api-pedidos" not in conteudo


@pytest.mark.django_db
def test_portfolio_mostra_linguagem_e_tecnologias_do_projeto_avaliado(client, estudante, empresa, submissao, github):
    analyze_snapshot(freeze_submission(submissao))
    Evaluation.objects.create(
        submission=submissao, evaluated_by=empresa.user, score=90, strengths="Muito bom trabalho.",
    )
    client.force_login(empresa.user)

    conteudo = client.get(reverse("portfolio:detail", args=[estudante.username])).content.decode()

    assert "Python" in conteudo
    assert "Django" in conteudo


@pytest.mark.django_db
def test_exportacao_de_dados_traz_o_commit_registrado(client, estudante, submissao, github):
    freeze_submission(submissao)
    client.force_login(estudante)

    dados = client.get(reverse("my_data_export")).json()

    assert dados["submissoes"][0]["commit_registrado"] == SHA
