"""
Testes de integração do ranking de estudantes (RF14), do portfólio público e do perfil
do estudante (RF15).
"""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile, User
from challenges.models import Challenge, Evaluation, Submission
from portfolio.services import portfolio_do_estudante, ranking_estudantes

D = Challenge.Difficulty


def _aluno(username):
    return User.objects.create_user(
        username=username, password="senha-teste-123", role=User.Role.STUDENT, email=f"{username}@email.com",
    )


def _desafio(empresa, titulo, dificuldade=D.BEGINNER):
    return Challenge.objects.create(
        company=empresa, title=titulo, description="x", difficulty=dificuldade,
        deadline=timezone.now() - timedelta(days=1), status=Challenge.Status.CLOSED,
    )


def _avaliada(desafio, aluno, nota, empresa):
    submissao = Submission.objects.create(
        challenge=desafio, student=aluno, repo_url="https://github.com/a/b", description="Solução",
    )
    Evaluation.objects.create(
        submission=submissao, evaluated_by=empresa.user, score=nota,
        strengths="Feedback reservado ao estudante.", improvements="Ponto a melhorar reservado.",
    )
    return submissao


@pytest.fixture
def cenario(empresa):
    facil, medio, dificil = (
        _desafio(empresa, "Fácil"),
        _desafio(empresa, "Médio", D.INTERMEDIATE),
        _desafio(empresa, "Difícil", D.ADVANCED),
    )
    ana, bruno, caio, dani = _aluno("ana"), _aluno("bruno"), _aluno("caio"), _aluno("dani")
    _avaliada(dificil, ana, 100, empresa)   # ana: 300 pontos, média 100
    _avaliada(medio, bruno, 90, empresa)    # bruno: 180 + 60 = 240 pontos, média 75
    _avaliada(facil, bruno, 60, empresa)
    _avaliada(medio, caio, 80, empresa)     # caio: 160 + 80 = 240 pontos, média 80 -> à frente de bruno
    _avaliada(facil, caio, 80, empresa)
    _avaliada(facil, dani, 100, empresa)    # dani: nota máxima, mas em desafio fácil: 100 pontos
    _aluno("sem_avaliacao")
    return {"ana": ana, "bruno": bruno, "caio": caio, "dani": dani, "facil": facil}


# ---------- Ranking (RF14) ----------

@pytest.mark.django_db
def test_ranking_deveOrdenarPorPontosEDesempatarPelaMedia(cenario):
    ranking = list(ranking_estudantes())

    assert [aluno.username for aluno in ranking] == ["ana", "caio", "bruno", "dani"]
    assert [aluno.pontos for aluno in ranking] == [300, 240, 240, 100]
    assert ranking[1].media == 80
    assert ranking[1].avaliacoes == 2


@pytest.mark.django_db
def test_ranking_empateEmPontosEMedia_deveSeguirOrdemAlfabetica(empresa):
    desafio = _desafio(empresa, "Único")
    _avaliada(desafio, _aluno("zeca"), 70, empresa)
    _avaliada(desafio, _aluno("bia"), 70, empresa)

    assert [aluno.username for aluno in ranking_estudantes()] == ["bia", "zeca"]


@pytest.mark.django_db
def test_ranking_naoMostraContaDesativada(cenario):
    User.objects.filter(pk=cenario["ana"].pk).update(is_active=False)

    assert "ana" not in [aluno.username for aluno in ranking_estudantes()]


@pytest.mark.django_db
def test_ranking_naoMostraEstudanteComPortfolioPrivado(cenario):
    StudentProfile.objects.create(user=cenario["ana"], portfolio_public=False)

    assert [aluno.username for aluno in ranking_estudantes()] == ["caio", "bruno", "dani"]


@pytest.mark.django_db
def test_paginaRanking_semLogin_deveSerPublica(client, cenario):
    response = client.get(reverse("portfolio:ranking"))

    assert response.status_code == 200
    assert response.context["ranking"][0].username == "ana"
    pagina = response.content.decode()
    assert "300" in pagina
    assert "ana@email.com" not in pagina
    assert reverse("login") in pagina  # o visitante tem um caminho para entrar


@pytest.mark.django_db
def test_paginaRanking_vazio_deveExplicar(client):
    response = client.get(reverse("portfolio:ranking"))

    assert "Ranking vazio" in response.content.decode()


# ---------- Portfólio (RF15) ----------

@pytest.mark.django_db
def test_portfolio_deveTrazerPontosMediaPosicaoESoAsAvaliadas(cenario, empresa):
    caio = cenario["caio"]
    Submission.objects.create(
        challenge=_desafio(empresa, "Sem nota"), student=caio, repo_url="https://github.com/a/c", description="x",
    )

    dados = portfolio_do_estudante(caio)

    assert dados["pontos"] == 240
    assert dados["media"] == 80
    assert dados["posicao"] == 2
    assert dados["total_submissoes"] == 3
    assert len(dados["avaliadas"]) == 2


@pytest.mark.django_db
def test_paginaPortfolio_semLogin_deveMostrarProjetosSemEmailNemFeedback(client, cenario):
    StudentProfile.objects.create(user=cenario["caio"], bio="Gosto de back-end.", github_username="caio-dev")

    response = client.get(reverse("portfolio:detail", args=["caio"]))

    assert response.status_code == 200
    pagina = response.content.decode()
    assert "Médio" in pagina and "Fácil" in pagina
    assert "160" in pagina  # pontos do projeto
    assert "Gosto de back-end." in pagina
    assert "https://github.com/caio-dev" in pagina
    assert "caio@email.com" not in pagina                    # RN52
    assert "Feedback reservado ao estudante." not in pagina  # o texto do feedback não é público


@pytest.mark.django_db
def test_paginaPortfolio_doProprioEstudante_deveMostrarOFeedback(client, cenario):
    client.force_login(cenario["caio"])

    pagina = client.get(reverse("portfolio:detail", args=["caio"])).content.decode()

    assert "Feedback reservado ao estudante." in pagina
    assert reverse("portfolio:edit_profile") in pagina


@pytest.mark.django_db
def test_paginaPortfolio_privado_deveRetornar404ParaOsOutrosEAbrirParaODono(client, empresa, cenario):
    StudentProfile.objects.create(user=cenario["caio"], portfolio_public=False)
    url = reverse("portfolio:detail", args=["caio"])

    assert client.get(url).status_code == 404  # visitante
    client.force_login(empresa.user)
    assert client.get(url).status_code == 404  # outro usuário autenticado
    client.force_login(cenario["caio"])
    resposta = client.get(url)
    assert resposta.status_code == 200
    assert "privado" in resposta.content.decode()


@pytest.mark.django_db
def test_paginaPortfolio_deEmpresaOuInexistente_deveRetornar404(client, empresa):
    assert client.get(reverse("portfolio:detail", args=[empresa.user.username])).status_code == 404
    assert client.get(reverse("portfolio:detail", args=["nao-existe"])).status_code == 404


# ---------- Meu perfil (RF15) ----------

@pytest.mark.django_db
def test_meuPerfil_deveGravarApresentacaoGithubEVisibilidade(client, estudante):
    client.force_login(estudante)

    response = client.post(reverse("portfolio:edit_profile"), {
        "bio": "Estudante de Engenharia de Software.", "github_username": "aluno-dev",
    })  # caixa "portfólio público" desmarcada não vai no POST

    assert response.status_code == 302
    perfil = StudentProfile.objects.get(user=estudante)
    assert perfil.bio == "Estudante de Engenharia de Software."
    assert perfil.github_username == "aluno-dev"
    assert perfil.portfolio_public is False


@pytest.mark.django_db
@pytest.mark.parametrize("valor", ["https://github.com/aluno", "@aluno", "aluno dev", "-aluno"])
def test_meuPerfil_usuarioDoGithubInvalido_deveMostrarErro(client, estudante, valor):
    client.force_login(estudante)

    response = client.post(reverse("portfolio:edit_profile"), {"github_username": valor, "portfolio_public": "on"})

    assert response.status_code == 200
    assert "github_username" in response.context["form"].errors


@pytest.mark.django_db
def test_meuPerfil_comoEmpresa_deveRedirecionar(client, empresa):
    client.force_login(empresa.user)

    response = client.get(reverse("portfolio:edit_profile"))

    assert response.status_code == 302
    assert not StudentProfile.objects.exists()


@pytest.mark.django_db
def test_meuPerfil_semLogin_deveRedirecionarParaOLogin(client):
    response = client.get(reverse("portfolio:edit_profile"))

    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_tornarPortfolioPrivado_deveTirarOEstudanteDoRanking(client, cenario):
    client.force_login(cenario["ana"])

    client.post(reverse("portfolio:edit_profile"), {"bio": "", "github_username": ""})

    assert "ana" not in [aluno.username for aluno in ranking_estudantes()]
    assert portfolio_do_estudante(cenario["ana"])["posicao"] is None
