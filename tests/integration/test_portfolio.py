"""
Testes de integração do ranking de estudantes e do portfólio.
"""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from challenges.models import Challenge, Evaluation, Submission
from portfolio.services import portfolio_do_estudante, ranking_estudantes


def _aluno(username):
    return User.objects.create_user(username=username, password="senha-teste-123", role=User.Role.STUDENT)


def _desafio(empresa, titulo):
    return Challenge.objects.create(
        company=empresa, title=titulo, description="x",
        deadline=timezone.now() + timedelta(days=7), status=Challenge.Status.OPEN,
    )


def _avaliada(desafio, aluno, nota, empresa):
    submissao = Submission.objects.create(
        challenge=desafio, student=aluno, repo_url="https://github.com/a/b", description="Solução",
    )
    Evaluation.objects.create(submission=submissao, evaluated_by=empresa.user, score=nota, feedback="Feedback de teste.")
    return submissao


@pytest.fixture
def cenario(empresa):
    d1, d2 = _desafio(empresa, "Desafio 1"), _desafio(empresa, "Desafio 2")
    ana, bruno, caio = _aluno("ana"), _aluno("bruno"), _aluno("caio")
    _avaliada(d1, ana, 8, empresa)
    _avaliada(d2, ana, 8, empresa)    # ana: média 8 com 2 avaliações
    _avaliada(d1, bruno, 8, empresa)  # bruno: média 8 com 1 avaliação -> perde no desempate
    _avaliada(d1, caio, 10, empresa)  # caio: média 10
    _aluno("sem_avaliacao")
    return {"ana": ana, "bruno": bruno, "caio": caio}


# ---------- Ranking ----------

@pytest.mark.django_db
def test_ranking_deveOrdenarPorMediaEDesempatarPorQuantidade(cenario):
    ranking = list(ranking_estudantes())

    assert [aluno.username for aluno in ranking] == ["caio", "ana", "bruno"]
    assert ranking[1].media == 8
    assert ranking[1].avaliacoes == 2


@pytest.mark.django_db
def test_ranking_naoMostraContaDesativada(cenario):
    User.objects.filter(pk=cenario["caio"].pk).update(is_active=False)

    assert "caio" not in [aluno.username for aluno in ranking_estudantes()]


@pytest.mark.django_db
def test_paginaRanking_deveListarEstudantes(client, estudante, cenario):
    client.force_login(estudante)

    response = client.get(reverse("portfolio:ranking"))

    assert response.status_code == 200
    assert list(response.context["ranking"])[0].username == "caio"


@pytest.mark.django_db
def test_paginaRanking_semLogin_deveRedirecionar(client):
    response = client.get(reverse("portfolio:ranking"))

    assert response.status_code == 302
    assert reverse("login") in response.url


# ---------- Portfólio ----------

@pytest.mark.django_db
def test_portfolio_deveTrazerMediaPosicaoESoAsAvaliadas(cenario, empresa):
    ana = cenario["ana"]
    Submission.objects.create(challenge=_desafio(empresa, "Sem nota"), student=ana, repo_url="https://github.com/a/c", description="x")

    dados = portfolio_do_estudante(ana)

    assert dados["media"] == 8
    assert dados["posicao"] == 2
    assert dados["total_submissoes"] == 3
    assert len(dados["avaliadas"]) == 2


@pytest.mark.django_db
def test_paginaPortfolio_deveRenderizar(client, empresa, cenario):
    client.force_login(empresa.user)

    response = client.get(reverse("portfolio:detail", args=["caio"]))

    assert response.status_code == 200
    assert "Desafio 1" in response.content.decode()


@pytest.mark.django_db
def test_paginaPortfolio_deEmpresaOuInexistente_deveRetornar404(client, estudante, empresa):
    client.force_login(estudante)

    assert client.get(reverse("portfolio:detail", args=[empresa.user.username])).status_code == 404
    assert client.get(reverse("portfolio:detail", args=["nao-existe"])).status_code == 404
