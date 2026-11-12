from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import CompanyProfile, User
from challenges.models import Challenge, Evaluation, Submission
from dashboard.services import DIAS_NA_SERIE, dashboard_data


def _numeros(data):
    return {item["rotulo"]: item["valor"] for item in data["big_numbers"]}


def _criar_empresa(username, nome, approved=True):
    user = User.objects.create_user(username=username, password="senha-teste-123", role=User.Role.COMPANY)
    return CompanyProfile.objects.create(user=user, company_name=nome, approved=approved)


def _criar_desafio(empresa, titulo, status=Challenge.Status.OPEN):
    return Challenge.objects.create(
        company=empresa, title=titulo, description="Descrição",
        deadline=timezone.now() + timedelta(days=7), status=status,
    )


def _submeter(desafio, estudante):
    return Submission.objects.create(
        challenge=desafio, student=estudante, repo_url="https://github.com/a/b", description="Solução",
    )


@pytest.fixture
def cenario(estudante, empresa, desafio_aberto):
    """Duas empresas, quatro desafios e três submissões, para conferir o filtro por perfil."""
    outra_empresa = _criar_empresa("outra", "Outra Tech")
    _criar_empresa("pendente", "Pendente SA", approved=False)
    rascunho = _criar_desafio(empresa, "Rascunho da Acme", Challenge.Status.DRAFT)
    desafio_da_outra = _criar_desafio(outra_empresa, "Desafio da Outra")
    _criar_desafio(outra_empresa, "Encerrado da Outra", Challenge.Status.CLOSED)
    outro_aluno = User.objects.create_user(username="aluno2", password="senha-teste-123", role=User.Role.STUDENT)

    _submeter(desafio_aberto, estudante)
    _submeter(desafio_aberto, outro_aluno)
    _submeter(desafio_da_outra, outro_aluno)
    return {"outra_empresa": outra_empresa, "rascunho": rascunho, "desafio_da_outra": desafio_da_outra}


# ---------- Acesso ----------

@pytest.mark.django_db
def test_dashboard_semLogin_deveRedirecionarParaLogin(client):
    response = client.get(reverse("dashboard:index"))

    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_apiDados_semLogin_deveRetornar403(client):
    response = client.get(reverse("dashboard:api_dados"))

    assert response.status_code == 403


# ---------- Big Numbers por perfil ----------

@pytest.mark.django_db
def test_bigNumbers_comoAdmin_deveMostrarTotaisDaPlataforma(cenario):
    admin = User.objects.create_superuser(username="admin", password="senha-teste-123")

    data = dashboard_data(admin)

    assert data["perfil"] == "ADMIN"
    assert _numeros(data) == {
        "Desafios abertos": 2,
        "Submissões": 3,
        "Estudantes": 2,
        "Empresas aguardando aprovação": 1,
        "Avaliações feitas": 0,
    }


@pytest.mark.django_db
def test_bigNumbers_comoEmpresa_deveContarSoOsProprioDesafios(cenario, empresa):
    data = dashboard_data(empresa.user)

    assert data["perfil"] == User.Role.COMPANY
    assert _numeros(data) == {
        "Desafios publicados": 2,
        "Desafios abertos": 1,
        "Submissões recebidas": 2,
        "Estudantes participantes": 2,
        "Aguardando avaliação": 2,
    }


@pytest.mark.django_db
def test_bigNumbers_comoEstudante_deveMostrarSuaParticipacao(cenario, estudante):
    data = dashboard_data(estudante)

    assert data["perfil"] == User.Role.STUDENT
    assert _numeros(data) == {
        "Submissões enviadas": 1,
        "Desafios abertos": 2,
        "Abertos sem a sua submissão": 1,
        "Nota média": None,
    }
    assert data["top_desafios"] == []


@pytest.mark.django_db
def test_bigNumbers_desafioComPrazoVencido_naoContaComoAberto(empresa, estudante):
    vencido = _criar_desafio(empresa, "Vencido")
    Challenge.objects.filter(pk=vencido.pk).update(deadline=timezone.now() - timedelta(days=1))

    assert _numeros(dashboard_data(estudante))["Desafios abertos"] == 0


@pytest.mark.django_db
def test_bigNumbers_estudanteAvaliado_deveMostrarNotaMedia(empresa, estudante, desafio_aberto):
    outro = _criar_desafio(empresa, "Outro")
    for desafio, nota in [(desafio_aberto, 7), (outro, 8)]:
        Evaluation.objects.create(submission=_submeter(desafio, estudante), evaluated_by=empresa.user, score=nota, feedback="Bom trabalho.")

    assert _numeros(dashboard_data(estudante))["Nota média"] == 7.5


# ---------- Séries dos gráficos ----------

@pytest.mark.django_db
def test_submissoesPorDia_deveTer30DiasEIgnorarSubmissaoAntiga(empresa, estudante, desafio_aberto):
    _submeter(desafio_aberto, estudante)
    antiga = _submeter(_criar_desafio(empresa, "Antigo"), estudante)
    Submission.objects.filter(pk=antiga.pk).update(submitted_at=timezone.now() - timedelta(days=DIAS_NA_SERIE + 5))

    serie = dashboard_data(estudante)["submissoes_por_dia"]

    assert len(serie) == DIAS_NA_SERIE
    assert serie[-1] == {"label": timezone.localdate().strftime("%d/%m"), "valor": 1}
    assert sum(ponto["valor"] for ponto in serie) == 1


@pytest.mark.django_db
def test_desafiosPorStatus_comoAdmin_deveContarCadaStatusNaOrdemDoModel(cenario):
    admin = User.objects.create_superuser(username="admin", password="senha-teste-123")

    serie = dashboard_data(admin)["desafios_por_status"]

    assert serie == [
        {"label": "Rascunho", "valor": 1},
        {"label": "Aberto", "valor": 2},
        {"label": "Encerrado", "valor": 1},
    ]


@pytest.mark.django_db
def test_topDesafios_comoAdmin_deveOrdenarPorQuantidadeDeSubmissoes(cenario):
    admin = User.objects.create_superuser(username="admin", password="senha-teste-123")

    top = dashboard_data(admin)["top_desafios"]

    assert top[0] == {"label": "API de pedidos", "valor": 2}
    assert top[1] == {"label": "Desafio da Outra", "valor": 1}


# ---------- Página e endpoint JSON ----------

@pytest.mark.django_db
def test_dashboard_comoEmpresa_deveRenderizarBigNumbersEGraficos(client, cenario, empresa):
    client.force_login(empresa.user)

    response = client.get(reverse("dashboard:index"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "Submissões recebidas" in body
    assert 'id="chart-submissoes"' in body
    assert 'id="chart-top"' in body
    assert "chart.umd.min.js" in body


@pytest.mark.django_db
def test_apiDados_comoEmpresa_deveRetornarJsonFiltradoPeloPerfil(client, cenario, empresa):
    client.force_login(empresa.user)

    response = client.get(reverse("dashboard:api_dados"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    data = response.json()
    assert data == dashboard_data(empresa.user)
    titulos = [ponto["label"] for ponto in data["top_desafios"]]
    assert "Desafio da Outra" not in titulos
