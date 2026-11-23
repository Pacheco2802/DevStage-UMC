"""
Testes de integração da área administrativa: as regras do ciclo de vida do desafio (RN21 e RN22)
e da avaliação (RN44) valem também em /admin/, e a correção de uma nota fica registrada na
auditoria com o valor anterior e o novo.
"""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from challenges.models import Challenge, Evaluation, Submission

PONTOS_FORTES = "Código organizado e fácil de acompanhar."


@pytest.fixture(autouse=True)
def estaticos_sem_manifesto(settings):
    # Em produção os estáticos passam pelo collectstatic; no teste, a página usa os arquivos direto
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def admin(db):
    return User.objects.create_superuser(username="admin", password="senha-teste-123")


@pytest.fixture
def painel(client, admin):
    client.force_login(admin)
    return client


@pytest.fixture
def submissao(estudante, desafio_aberto):
    return Submission.objects.create(
        challenge=desafio_aberto, student=estudante,
        repo_url="https://github.com/aluno/api", description="Minha solução",
    )


@pytest.fixture
def avaliacao(submissao, empresa):
    Challenge.objects.filter(pk=submissao.challenge_id).update(
        status=Challenge.Status.CLOSED, difficulty=Challenge.Difficulty.INTERMEDIATE,
    )
    submissao.challenge.refresh_from_db()
    return Evaluation.objects.create(
        submission=submissao, evaluated_by=empresa.user, score=70, strengths=PONTOS_FORTES,
    )


def _dados_do_desafio(desafio, **alteracoes):
    """O que a tela de edição do admin envia: todos os campos, com o prazo em data e hora."""
    prazo = timezone.localtime(desafio.deadline)
    dados = {
        "company": desafio.company_id,
        "title": desafio.title,
        "description": desafio.description,
        "deadline_0": prazo.strftime("%Y-%m-%d"),
        "deadline_1": prazo.strftime("%H:%M:%S"),
        "difficulty": desafio.difficulty,
        "status": desafio.status,
    }
    dados.update(alteracoes)
    return dados


def _editar_desafio(painel, desafio, **alteracoes):
    url = reverse("admin:challenges_challenge_change", args=[desafio.pk])
    return painel.post(url, _dados_do_desafio(desafio, **alteracoes))


# ---------- RN21: as transições de situação valem também no admin ----------

@pytest.mark.django_db
def test_admin_naoReabreDesafioEncerrado(painel, desafio_aberto):
    Challenge.objects.filter(pk=desafio_aberto.pk).update(status=Challenge.Status.CLOSED)
    desafio_aberto.refresh_from_db()

    resposta = _editar_desafio(painel, desafio_aberto, status=Challenge.Status.OPEN)

    desafio_aberto.refresh_from_db()
    assert desafio_aberto.status == Challenge.Status.CLOSED
    assert "não pode passar para" in resposta.content.decode()


@pytest.mark.django_db
def test_admin_naoDevolveDesafioAbertoParaRascunho(painel, desafio_aberto):
    _editar_desafio(painel, desafio_aberto, status=Challenge.Status.DRAFT)

    desafio_aberto.refresh_from_db()
    assert desafio_aberto.status == Challenge.Status.OPEN


@pytest.mark.django_db
def test_admin_naoPublicaRascunhoComPrazoVencido(painel, desafio_aberto):
    Challenge.objects.filter(pk=desafio_aberto.pk).update(
        status=Challenge.Status.DRAFT, deadline=timezone.now() - timedelta(days=1),
    )
    desafio_aberto.refresh_from_db()

    resposta = _editar_desafio(painel, desafio_aberto, status=Challenge.Status.OPEN)

    desafio_aberto.refresh_from_db()
    assert desafio_aberto.status == Challenge.Status.DRAFT
    assert "O prazo deste desafio já passou" in resposta.content.decode()


@pytest.mark.django_db
def test_admin_encerraDesafioAberto(painel, desafio_aberto, submissao):
    resposta = _editar_desafio(painel, desafio_aberto, status=Challenge.Status.CLOSED)

    desafio_aberto.refresh_from_db()
    assert resposta.status_code == 302
    assert desafio_aberto.status == Challenge.Status.CLOSED


# ---------- RN22: depois da primeira entrega as condições ficam congeladas ----------

@pytest.mark.django_db
def test_admin_naoTrocaDificuldadeNemPrazoDepoisDaPrimeiraEntrega(painel, desafio_aberto, submissao):
    prazo_original = desafio_aberto.deadline
    novo_prazo = timezone.localtime(prazo_original + timedelta(days=30))

    _editar_desafio(
        painel, desafio_aberto,
        difficulty=Challenge.Difficulty.ADVANCED,
        deadline_0=novo_prazo.strftime("%Y-%m-%d"),
        title="Outro título",
    )

    desafio_aberto.refresh_from_db()
    assert desafio_aberto.difficulty == Challenge.Difficulty.BEGINNER
    assert desafio_aberto.deadline == prazo_original
    assert desafio_aberto.title == "API de pedidos"


@pytest.mark.django_db
def test_admin_editaDesafioAbertoSemEntregas(painel, desafio_aberto):
    resposta = _editar_desafio(painel, desafio_aberto, difficulty=Challenge.Difficulty.ADVANCED)

    desafio_aberto.refresh_from_db()
    assert resposta.status_code == 302
    assert desafio_aberto.difficulty == Challenge.Difficulty.ADVANCED


# ---------- Exclusão: o que já tem entrega ou nota não é apagado pelo admin ----------

@pytest.mark.django_db
def test_admin_naoExcluiDesafioComEntregas(painel, desafio_aberto, submissao):
    painel.post(reverse("admin:challenges_challenge_delete", args=[desafio_aberto.pk]), {"post": "yes"})

    assert Challenge.objects.filter(pk=desafio_aberto.pk).exists()
    assert Submission.objects.filter(pk=submissao.pk).exists()


@pytest.mark.django_db
def test_admin_naoExcluiDesafioComEntregasPelaAcaoEmLote(painel, desafio_aberto, submissao):
    painel.post(reverse("admin:challenges_challenge_changelist"), {
        "action": "delete_selected", "_selected_action": [desafio_aberto.pk], "post": "yes",
    })

    assert Challenge.objects.filter(pk=desafio_aberto.pk).exists()
    assert Submission.objects.filter(pk=submissao.pk).exists()


@pytest.mark.django_db
def test_admin_excluiDesafioSemEntregas(painel, desafio_aberto):
    painel.post(reverse("admin:challenges_challenge_delete", args=[desafio_aberto.pk]), {"post": "yes"})

    assert not Challenge.objects.filter(pk=desafio_aberto.pk).exists()


@pytest.mark.django_db
def test_admin_naoAlteraEntrega(painel, submissao):
    painel.post(reverse("admin:challenges_submission_change", args=[submissao.pk]), {
        "challenge": submissao.challenge_id, "student": submissao.student_id,
        "repo_url": "https://github.com/aluno/outro-repositorio", "description": "Trocada",
    })

    submissao.refresh_from_db()
    assert submissao.repo_url == "https://github.com/aluno/api"


@pytest.mark.django_db
def test_admin_naoExcluiEntrega(painel, submissao):
    painel.post(reverse("admin:challenges_submission_delete", args=[submissao.pk]), {"post": "yes"})

    assert Submission.objects.filter(pk=submissao.pk).exists()


@pytest.mark.django_db
def test_admin_naoExcluiAvaliacao(painel, avaliacao):
    painel.post(reverse("admin:challenges_evaluation_delete", args=[avaliacao.pk]), {"post": "yes"})

    assert Evaluation.objects.filter(pk=avaliacao.pk).exists()


@pytest.mark.django_db
def test_admin_naoExcluiEstudanteComEntregaAvaliada(painel, estudante, avaliacao):
    painel.post(reverse("admin:accounts_user_delete", args=[estudante.pk]), {"post": "yes"})

    assert User.objects.filter(pk=estudante.pk).exists()
    assert Evaluation.objects.filter(pk=avaliacao.pk).exists()


# ---------- RN44: a correção da nota fica na auditoria com o valor anterior e o novo ----------

def _corrigir_nota(painel, avaliacao, nota):
    return painel.post(reverse("admin:challenges_evaluation_change", args=[avaliacao.pk]), {
        "score": nota, "strengths": avaliacao.strengths, "improvements": avaliacao.improvements,
    }, REMOTE_ADDR="10.0.0.9")


@pytest.mark.django_db
def test_corrigirNotaNoAdmin_deveRegistrarNotaAnteriorENova(painel, admin, avaliacao):
    _corrigir_nota(painel, avaliacao, 85)

    avaliacao.refresh_from_db()
    registro = AuditLog.objects.filter(target_model="Evaluation", action=AuditLog.Action.UPDATE).first()
    assert avaliacao.score == 85
    assert avaliacao.points == 170
    assert registro.user == admin
    assert registro.ip == "10.0.0.9"
    assert registro.changes == {"score": [70, 85], "points": [140, 170]}


@pytest.mark.django_db
def test_corrigirSoOFeedback_naoRegistraMudancaDeNota(painel, avaliacao):
    painel.post(reverse("admin:challenges_evaluation_change", args=[avaliacao.pk]), {
        "score": 70, "strengths": "Texto dos pontos fortes reescrito pelo administrador.", "improvements": "",
    })

    registro = AuditLog.objects.filter(target_model="Evaluation", action=AuditLog.Action.UPDATE).first()
    assert registro.changes == {}


@pytest.mark.django_db
def test_criarAvaliacao_naoTemValorAnteriorNaAuditoria(avaliacao):
    registro = AuditLog.objects.filter(target_model="Evaluation", action=AuditLog.Action.CREATE).first()

    assert registro.changes == {}


@pytest.mark.django_db
def test_encerrarDesafio_deveRegistrarASituacaoAnteriorEANova(client, empresa, desafio_aberto):
    client.force_login(empresa.user)

    client.post(reverse("challenges:close", args=[desafio_aberto.pk]))

    registro = AuditLog.objects.filter(target_model="Challenge", action=AuditLog.Action.UPDATE).first()
    assert registro.changes == {"status": ["OPEN", "CLOSED"]}


@pytest.mark.django_db
def test_admin_mostraOValorAnteriorEONovoNoRegistroDeAuditoria(painel, avaliacao):
    _corrigir_nota(painel, avaliacao, 85)
    registro = AuditLog.objects.filter(target_model="Evaluation", action=AuditLog.Action.UPDATE).first()

    pagina = painel.get(reverse("admin:audit_auditlog_change", args=[registro.pk])).content.decode()

    assert "Nota: 70 → 85" in pagina
    assert "Pontos: 140 → 170" in pagina
