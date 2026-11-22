"""
Testes de integração da avaliação de submissões (RF12) e da pontuação (RF13),
além da visibilidade de desafios em rascunho.
"""
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from accounts.models import CompanyProfile, User
from challenges.models import Challenge, Evaluation, Submission

PONTOS_FORTES = "Boa organização do código e testes claros."
A_MELHORAR = "Faltou tratar as entradas duplicadas no cadastro."


@pytest.fixture
def desafio_no_prazo(empresa):
    return Challenge.objects.create(
        company=empresa, title="API de pedidos", description="Construa uma API REST de pedidos.",
        deadline=timezone.now() + timedelta(days=7), status=Challenge.Status.OPEN,
        difficulty=Challenge.Difficulty.INTERMEDIATE,
    )


@pytest.fixture
def submissao(estudante, desafio_no_prazo):
    """Submissão de um desafio Intermediário (peso 2) cujo prazo já terminou: pronta para avaliar."""
    entrega = Submission.objects.create(
        challenge=desafio_no_prazo, student=estudante,
        repo_url="https://github.com/aluno/api", description="Minha solução",
    )
    Challenge.objects.filter(pk=desafio_no_prazo.pk).update(deadline=timezone.now() - timedelta(hours=1))
    entrega.refresh_from_db()
    return entrega


def _avaliar(client, submissao, score, strengths=PONTOS_FORTES, improvements=A_MELHORAR):
    return client.post(
        reverse("challenges:evaluate", args=[submissao.pk]),
        {"score": score, "strengths": strengths, "improvements": improvements},
    )


# ---------- Avaliar ----------

@pytest.mark.django_db
def test_avaliar_comoEmpresaDona_deveSalvarNotaEFeedbackDividido(client, empresa, submissao):
    client.force_login(empresa.user)

    response = _avaliar(client, submissao, 85)

    assert response.status_code == 302
    assert response.url == reverse("challenges:submissions", args=[submissao.challenge.pk])
    avaliacao = Evaluation.objects.get(submission=submissao)
    assert avaliacao.score == 85
    assert avaliacao.strengths == PONTOS_FORTES
    assert avaliacao.improvements == A_MELHORAR
    assert avaliacao.evaluated_by == empresa.user


@pytest.mark.django_db
@pytest.mark.parametrize("nota", [-1, 101, ""])
def test_avaliar_notaForaDaFaixa_deveMostrarErroENaoSalvar(client, empresa, submissao, nota):
    client.force_login(empresa.user)

    response = _avaliar(client, submissao, nota)

    assert response.status_code == 200
    assert "score" in response.context["form"].errors
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("nota", [0, 100])
def test_avaliar_notaNosLimitesDaFaixa_deveSalvar(client, empresa, submissao, nota):
    client.force_login(empresa.user)

    _avaliar(client, submissao, nota)

    assert Evaluation.objects.get(submission=submissao).score == nota


@pytest.mark.django_db
@pytest.mark.parametrize("campo", ["strengths", "improvements"])
def test_avaliar_feedbackComMenosDe20Caracteres_deveMostrarErroNoCampo(client, empresa, submissao, campo):
    client.force_login(empresa.user)
    textos = {"strengths": PONTOS_FORTES, "improvements": A_MELHORAR, campo: "muito curto"}

    response = _avaliar(client, submissao, 70, **textos)

    assert response.status_code == 200
    assert list(response.context["form"].errors) == [campo]
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_avaliar_feedbackSoComEspacos_naoContaComoTexto(client, empresa, submissao):
    client.force_login(empresa.user)

    response = _avaliar(client, submissao, 70, improvements=" " * 40)

    assert "improvements" in response.context["form"].errors
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_avaliar_submissaoDeOutraEmpresa_deveRetornar404(client, submissao):
    outra = User.objects.create_user(username="outra", password="senha-teste-123", role=User.Role.COMPANY)
    CompanyProfile.objects.create(user=outra, company_name="Outra", approved=True)
    client.force_login(outra)

    response = _avaliar(client, submissao, 100)

    assert response.status_code == 404
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_avaliar_comoEstudante_deveRedirecionarSemSalvar(client, estudante, submissao):
    client.force_login(estudante)

    response = _avaliar(client, submissao, 100)

    assert response.status_code == 302
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_banco_recusaNotaForaDaFaixaMesmoSemForm(submissao, empresa):
    with pytest.raises(IntegrityError):
        Evaluation.objects.create(
            submission=submissao, evaluated_by=empresa.user, score=150, strengths=PONTOS_FORTES,
        )


# ---------- RN41: só depois do prazo ou do encerramento ----------

@pytest.mark.django_db
def test_avaliar_comPrazoEmAndamento_deveRecusarEInformarOMotivo(client, empresa, estudante, desafio_no_prazo):
    entrega = Submission.objects.create(
        challenge=desafio_no_prazo, student=estudante,
        repo_url="https://github.com/aluno/api", description="Minha solução",
    )
    client.force_login(empresa.user)

    response = _avaliar(client, entrega, 90)

    assert response.status_code == 302
    assert not Evaluation.objects.exists()
    pagina = client.get(response.url)
    assert "A avaliação só é liberada depois do prazo ou do encerramento do desafio." in pagina.content.decode()
    assert pagina.context["form"] is None  # a entrega é exibida, mas sem o formulário


@pytest.mark.django_db
def test_avaliar_desafioEncerradoAntesDoPrazo_devePermitir(client, empresa, estudante, desafio_no_prazo):
    entrega = Submission.objects.create(
        challenge=desafio_no_prazo, student=estudante,
        repo_url="https://github.com/aluno/api", description="Minha solução",
    )
    Challenge.objects.filter(pk=desafio_no_prazo.pk).update(status=Challenge.Status.CLOSED)
    client.force_login(empresa.user)

    _avaliar(client, entrega, 90)

    assert Evaluation.objects.filter(submission=entrega).exists()


# ---------- RN44: uma avaliação, sem alteração pela empresa ----------

@pytest.mark.django_db
def test_avaliar_submissaoJaAvaliada_deveRecusarEManterAPrimeiraNota(client, empresa, submissao):
    client.force_login(empresa.user)
    _avaliar(client, submissao, 60)

    response = _avaliar(client, submissao, 95)

    assert response.status_code == 302
    avaliacao = Evaluation.objects.get(submission=submissao)
    assert avaliacao.score == 60
    pagina = client.get(response.url).content.decode()
    assert "Esta submissão já foi avaliada." in pagina
    assert "<form method=\"post\" class=\"card" not in pagina


@pytest.mark.django_db
def test_banco_recusaSegundaAvaliacaoDaMesmaSubmissao(submissao, empresa):
    Evaluation.objects.create(submission=submissao, evaluated_by=empresa.user, score=70, strengths=PONTOS_FORTES)

    with pytest.raises(IntegrityError):
        Evaluation.objects.create(submission=submissao, evaluated_by=empresa.user, score=80, strengths=PONTOS_FORTES)


@pytest.mark.django_db
def test_admin_corrigeANota_devemRecalcularOsPontosComOPesoOriginal(submissao, empresa):
    avaliacao = Evaluation.objects.create(
        submission=submissao, evaluated_by=empresa.user, score=70, strengths=PONTOS_FORTES,
    )

    avaliacao.score = 90  # correção feita pelo administrador, na área administrativa
    avaliacao.save()

    avaliacao.refresh_from_db()
    assert avaliacao.points == 180


# ---------- RF13: pontos = nota x peso da dificuldade ----------

@pytest.mark.django_db
@pytest.mark.parametrize("dificuldade, nota, pontos", [
    [Challenge.Difficulty.BEGINNER, 80, 80],
    [Challenge.Difficulty.INTERMEDIATE, 80, 160],
    [Challenge.Difficulty.ADVANCED, 100, 300],
    [Challenge.Difficulty.ADVANCED, 0, 0],
])
def test_avaliar_deveGravarPontosComoNotaVezesPeso(client, empresa, submissao, dificuldade, nota, pontos):
    Challenge.objects.filter(pk=submissao.challenge.pk).update(difficulty=dificuldade)
    client.force_login(empresa.user)

    _avaliar(client, submissao, nota)

    assert Evaluation.objects.get(submission=submissao).points == pontos


@pytest.mark.django_db
def test_pontos_naoMudamSeADificuldadeDoDesafioForAlteradaDepois(submissao, empresa):
    avaliacao = Evaluation.objects.create(
        submission=submissao, evaluated_by=empresa.user, score=80, strengths=PONTOS_FORTES,
    )
    assert avaliacao.points == 160

    Challenge.objects.filter(pk=submissao.challenge.pk).update(difficulty=Challenge.Difficulty.ADVANCED)
    avaliacao = Evaluation.objects.get(pk=avaliacao.pk)
    avaliacao.save()  # mesmo regravando a avaliação, vale o peso de quando ela foi criada

    assert Evaluation.objects.get(pk=avaliacao.pk).points == 160


# ---------- Estudante vê o resultado ----------

@pytest.mark.django_db
def test_minhasSubmissoes_deveMostrarNotaPontosEAsDuasPartesDoFeedback(client, empresa, estudante, submissao):
    Evaluation.objects.create(
        submission=submissao, evaluated_by=empresa.user, score=75,
        strengths=PONTOS_FORTES, improvements=A_MELHORAR,
    )
    client.force_login(estudante)

    response = client.get(reverse("challenges:my_submissions"))

    body = response.content.decode()
    assert PONTOS_FORTES in body
    assert A_MELHORAR in body
    assert ">75<" in body
    assert "150 pontos" in body


@pytest.mark.django_db
def test_minhasSubmissoes_semAvaliacao_deveMostrarAguardando(client, estudante, submissao):
    client.force_login(estudante)

    response = client.get(reverse("challenges:my_submissions"))

    assert "Aguardando avaliação" in response.content.decode()


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


# ---------- Corrida entre duas requisições: quem garante a regra é o banco ----------

@pytest.mark.django_db
def test_avaliar_quandoOutraRequisicaoGravouPrimeiro_deveRecusarSemErro(client, empresa, submissao, monkeypatch):
    Evaluation.objects.create(submission=submissao, evaluated_by=empresa.user, score=60, strengths=PONTOS_FORTES)
    # Simula o segundo envio de um clique duplo: passou pela verificação da view antes de o
    # primeiro gravar, e só a relação um para um do banco o impede
    monkeypatch.setattr("challenges.views._check_can_evaluate", lambda *args: "")
    client.force_login(empresa.user)

    response = _avaliar(client, submissao, 95)

    assert response.status_code == 302
    assert Evaluation.objects.get(submission=submissao).score == 60
