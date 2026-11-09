"""
Testes de integração da avaliação de submissões (nota 0-10 + feedback) e da
visibilidade de desafios em rascunho.
"""
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from accounts.models import CompanyProfile, User
from challenges.models import Challenge, Evaluation, Submission

FEEDBACK = "Boa organização do código e testes claros."


@pytest.fixture
def submissao(estudante, desafio_aberto):
    return Submission.objects.create(
        challenge=desafio_aberto, student=estudante,
        repo_url="https://github.com/aluno/api", description="Minha solução",
    )


def _avaliar(client, submissao, score, feedback=FEEDBACK):
    return client.post(reverse("challenges:evaluate", args=[submissao.pk]), {"score": score, "feedback": feedback})


# ---------- Avaliar ----------

@pytest.mark.django_db
def test_avaliar_comoEmpresaDona_deveSalvarNotaEFeedback(client, empresa, submissao):
    client.force_login(empresa.user)

    response = _avaliar(client, submissao, 8)

    assert response.status_code == 302
    assert response.url == reverse("challenges:submissions", args=[submissao.challenge.pk])
    avaliacao = Evaluation.objects.get(submission=submissao)
    assert avaliacao.score == 8
    assert avaliacao.feedback == FEEDBACK
    assert avaliacao.evaluated_by == empresa.user


@pytest.mark.django_db
def test_avaliar_novamente_deveEditarAMesmaAvaliacao(client, empresa, submissao):
    client.force_login(empresa.user)
    _avaliar(client, submissao, 6)

    _avaliar(client, submissao, 9, "Corrigiu os pontos levantados, ótimo.")

    assert Evaluation.objects.filter(submission=submissao).count() == 1
    assert Evaluation.objects.get(submission=submissao).score == 9


@pytest.mark.django_db
@pytest.mark.parametrize("nota", [-1, 11, ""])
def test_avaliar_notaForaDaFaixa_deveMostrarErroENaoSalvar(client, empresa, submissao, nota):
    client.force_login(empresa.user)

    response = _avaliar(client, submissao, nota)

    assert response.status_code == 200
    assert "score" in response.context["form"].errors
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_avaliar_feedbackCurto_deveMostrarErro(client, empresa, submissao):
    client.force_login(empresa.user)

    response = _avaliar(client, submissao, 7, "ok")

    assert response.status_code == 200
    assert "feedback" in response.context["form"].errors
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_avaliar_submissaoDeOutraEmpresa_deveRetornar404(client, submissao):
    outra = User.objects.create_user(username="outra", password="senha-teste-123", role=User.Role.COMPANY)
    CompanyProfile.objects.create(user=outra, company_name="Outra", approved=True)
    client.force_login(outra)

    response = _avaliar(client, submissao, 10)

    assert response.status_code == 404
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_avaliar_comoEstudante_deveRedirecionarSemSalvar(client, estudante, submissao):
    client.force_login(estudante)

    response = _avaliar(client, submissao, 10)

    assert response.status_code == 302
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_banco_recusaNotaForaDaFaixaMesmoSemForm(submissao, empresa):
    with pytest.raises(IntegrityError):
        Evaluation.objects.create(submission=submissao, evaluated_by=empresa.user, score=15, feedback=FEEDBACK)


# ---------- Estudante vê o resultado ----------

@pytest.mark.django_db
def test_minhasSubmissoes_deveMostrarNotaEFeedback(client, empresa, estudante, submissao):
    Evaluation.objects.create(submission=submissao, evaluated_by=empresa.user, score=7, feedback=FEEDBACK)
    client.force_login(estudante)

    response = client.get(reverse("challenges:my_submissions"))

    body = response.content.decode()
    assert FEEDBACK in body
    assert ">7<" in body


# ---------- Rascunho ----------

@pytest.mark.django_db
def test_detalhe_desafioRascunho_deveRetornar404ParaQuemNaoEDono(client, empresa, estudante):
    rascunho = Challenge.objects.create(
        company=empresa, title="Ainda em rascunho", description="x",
        deadline=timezone.now() + timedelta(days=3), status=Challenge.Status.DRAFT,
    )
    client.force_login(estudante)

    assert client.get(reverse("challenges:detail", args=[rascunho.pk])).status_code == 404

    client.force_login(empresa.user)
    assert client.get(reverse("challenges:detail", args=[rascunho.pk])).status_code == 200
