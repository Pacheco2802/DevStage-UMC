"""
Testes de integração do painel da empresa (meus desafios, edição, submissões recebidas)
e da página "Minhas submissões" do estudante.
"""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import CompanyProfile, User
from challenges.models import Challenge, Submission


def _criar_empresa(username, nome, approved=True):
    user = User.objects.create_user(username=username, password="senha-teste-123", role=User.Role.COMPANY)
    return CompanyProfile.objects.create(user=user, company_name=nome, approved=approved)


def _submeter(desafio, estudante, repo="https://github.com/a/b"):
    return Submission.objects.create(challenge=desafio, student=estudante, repo_url=repo, description="Solução")


@pytest.fixture
def desafio_da_outra():
    outra = _criar_empresa("outra", "Outra Tech")
    return Challenge.objects.create(
        company=outra, title="Desafio da Outra", description="Descrição",
        deadline=timezone.now() + timedelta(days=7), status=Challenge.Status.OPEN,
    )


# ---------- Meus desafios ----------

@pytest.mark.django_db
def test_meusDesafios_semLogin_deveRedirecionarParaLogin(client):
    response = client.get(reverse("challenges:mine"))

    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_meusDesafios_comoEstudante_deveRedirecionarParaLista(client, estudante):
    client.force_login(estudante)

    response = client.get(reverse("challenges:mine"))

    assert response.status_code == 302
    assert response.url == reverse("challenges:list")


@pytest.mark.django_db
def test_meusDesafios_comoEmpresa_deveListarSoOsPropriosComContagem(
    client, empresa, estudante, desafio_aberto, desafio_da_outra
):
    _submeter(desafio_aberto, estudante)
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:mine"))

    assert response.status_code == 200
    desafios = list(response.context["challenges"])
    assert desafios == [desafio_aberto]
    assert desafios[0].total_submissions == 1
    assert "Desafio da Outra" not in response.content.decode()


# ---------- Editar desafio ----------

@pytest.mark.django_db
def test_editar_get_deveTrazerPrazoNoFormatoDoInput(client, empresa, desafio_aberto):
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:edit", args=[desafio_aberto.pk]))

    assert response.status_code == 200
    prazo = timezone.localtime(desafio_aberto.deadline).strftime("%Y-%m-%dT%H:%M")
    assert f'value="{prazo}"' in response.content.decode()


@pytest.mark.django_db
def test_editar_postValido_deveEncerrarDesafio(client, empresa, desafio_aberto):
    client.force_login(empresa.user)
    prazo = timezone.localtime(desafio_aberto.deadline).strftime("%Y-%m-%dT%H:%M")

    response = client.post(reverse("challenges:edit", args=[desafio_aberto.pk]), {
        "title": "API de pedidos v2", "description": "Nova descrição",
        "deadline": prazo, "status": Challenge.Status.CLOSED,
    })

    assert response.status_code == 302
    assert response.url == reverse("challenges:mine")
    desafio_aberto.refresh_from_db()
    assert desafio_aberto.title == "API de pedidos v2"
    assert desafio_aberto.status == Challenge.Status.CLOSED


@pytest.mark.django_db
def test_editar_postSemTitulo_deveMostrarErroENaoSalvar(client, empresa, desafio_aberto):
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:edit", args=[desafio_aberto.pk]), {
        "title": "", "description": "x", "deadline": "", "status": Challenge.Status.CLOSED,
    })

    assert response.status_code == 200
    assert response.context["form"].errors.keys() >= {"title", "deadline"}
    desafio_aberto.refresh_from_db()
    assert desafio_aberto.status == Challenge.Status.OPEN


@pytest.mark.django_db
def test_editar_desafioDeOutraEmpresa_deveRetornar404(client, empresa, desafio_da_outra):
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:edit", args=[desafio_da_outra.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_editar_empresaNaoAprovada_deveRedirecionar(client, desafio_aberto):
    CompanyProfile.objects.filter(pk=desafio_aberto.company.pk).update(approved=False)
    client.force_login(desafio_aberto.company.user)

    response = client.get(reverse("challenges:edit", args=[desafio_aberto.pk]))

    assert response.status_code == 302
    assert response.url == reverse("challenges:list")


# ---------- Submissões recebidas ----------

@pytest.mark.django_db
def test_submissoes_comoDona_deveListarAsSubmissoesDoDesafio(client, empresa, estudante, desafio_aberto):
    _submeter(desafio_aberto, estudante, repo="https://github.com/aluno/api-pedidos")
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:submissions", args=[desafio_aberto.pk]))

    assert response.status_code == 200
    assert "https://github.com/aluno/api-pedidos" in response.content.decode()


@pytest.mark.django_db
def test_submissoes_desafioDeOutraEmpresa_deveRetornar404(client, empresa, desafio_da_outra):
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:submissions", args=[desafio_da_outra.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_submissoes_comoEstudante_deveRedirecionar(client, estudante, desafio_aberto):
    client.force_login(estudante)

    response = client.get(reverse("challenges:submissions", args=[desafio_aberto.pk]))

    assert response.status_code == 302


# ---------- Minhas submissões (estudante) ----------

@pytest.mark.django_db
def test_minhasSubmissoes_comoEstudante_deveListarSoAsProprias(client, estudante, desafio_aberto, desafio_da_outra):
    outro = User.objects.create_user(username="aluno2", password="senha-teste-123", role=User.Role.STUDENT)
    minha = _submeter(desafio_aberto, estudante)
    _submeter(desafio_da_outra, outro)
    client.force_login(estudante)

    response = client.get(reverse("challenges:my_submissions"))

    assert response.status_code == 200
    assert list(response.context["submissions"]) == [minha]


@pytest.mark.django_db
def test_minhasSubmissoes_comoEmpresa_deveRedirecionar(client, empresa):
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:my_submissions"))

    assert response.status_code == 302
    assert response.url == reverse("challenges:list")
