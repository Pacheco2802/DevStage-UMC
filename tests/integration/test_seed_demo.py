import pytest
from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import CompanyProfile, ConsentLog, StudentProfile, User
from challenges.models import Challenge, Evaluation, RepoSnapshot, Submission
from core.management.commands.seed_demo import DOMINIO_DEMO, VARIAVEL_SENHA
from portfolio.services import ranking_estudantes

SENHA = "senha-de-demonstracao-123"


@pytest.fixture(autouse=True)
def hash_rapido(settings):
    # O comando cria dezenas de contas; o hash padrão (PBKDF2) deixaria estes testes lentos
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def senha_definida(monkeypatch):
    monkeypatch.setenv(VARIAVEL_SENHA, SENHA)


def contas_demo():
    return User.objects.filter(email__endswith="@" + DOMINIO_DEMO)


@pytest.mark.django_db
def test_seedDemo_semSenhaDefinida_deveFalharSemCriarNada(monkeypatch):
    monkeypatch.delenv(VARIAVEL_SENHA, raising=False)

    with pytest.raises(CommandError):
        call_command("seed_demo")

    assert not contas_demo().exists()


@pytest.mark.django_db
def test_seedDemo_devePopularEmpresasDesafiosEstudantesERanking(senha_definida):
    call_command("seed_demo")

    assert CompanyProfile.objects.filter(approved=True).count() == 2
    assert CompanyProfile.objects.filter(approved=False).count() == 1
    assert Challenge.objects.filter(status=Challenge.Status.OPEN).count() == 3
    assert Challenge.objects.values("difficulty").distinct().count() == 3
    assert contas_demo().filter(role=User.Role.STUDENT).count() == 24
    assert Evaluation.objects.count() > 0
    # todo estudante de demonstração entra com a senha informada e tem o aceite dos termos registrado
    assert authenticate(username="rnunes", password=SENHA) is not None
    assert ConsentLog.objects.count() == contas_demo().count()
    # o pódio do ranking precisa de pelo menos três estudantes avaliados
    assert ranking_estudantes().count() >= 3
    # cada estudante tem o perfil do portfólio, e um deles é privado para demonstrar a opção
    assert StudentProfile.objects.count() == 24
    assert StudentProfile.objects.filter(portfolio_public=False).count() == 1


@pytest.mark.django_db
def test_seedDemo_soAvaliaDesafioEncerradoOuComPrazoVencido(senha_definida):
    call_command("seed_demo")

    for avaliacao in Evaluation.objects.select_related("submission__challenge"):
        desafio = avaliacao.submission.challenge
        assert desafio.accepts_evaluation
        assert avaliacao.points == avaliacao.score * desafio.weight
        assert len(avaliacao.strengths) >= 20 and len(avaliacao.improvements) >= 20
    # no desafio aberto com prazo vencido, parte das entregas ainda aguarda avaliação
    assert Submission.objects.filter(evaluation__isnull=True, challenge__status=Challenge.Status.OPEN).exists()


@pytest.mark.django_db
def test_seedDemo_naoEnviaSubmissaoParaRascunhoNemForaDoPeriodoDoDesafio(senha_definida):
    call_command("seed_demo")

    assert not Submission.objects.filter(challenge__status=Challenge.Status.DRAFT).exists()
    for submissao in Submission.objects.select_related("challenge"):
        assert submissao.challenge.created_at < submissao.submitted_at < submissao.challenge.deadline


@pytest.mark.django_db
def test_seedDemo_executadoDuasVezes_naoDuplicaDados(senha_definida):
    call_command("seed_demo")
    total_contas = contas_demo().count()
    total_submissoes = Submission.objects.count()

    call_command("seed_demo")

    assert contas_demo().count() == total_contas
    assert Submission.objects.count() == total_submissoes


@pytest.mark.django_db
def test_seedDemo_comUsuarioRealDeMesmoNome_naoAlteraAContaExistente(senha_definida):
    real = User.objects.create_user(username="msato", password="outra-senha-123", email="marina@empresa-real.com")

    call_command("seed_demo")

    real.refresh_from_db()
    assert real.email == "marina@empresa-real.com"
    assert authenticate(username="msato", password="outra-senha-123") is not None
    assert not real.submissions.exists()


@pytest.mark.django_db
def test_seedDemo_limpar_deveRemoverSoOsDadosDeDemonstracao(senha_definida, estudante, desafio_aberto):
    call_command("seed_demo")

    call_command("seed_demo", "--limpar")

    assert not contas_demo().exists()
    assert Submission.objects.count() == 0
    # a conta e o desafio que não são de demonstração continuam no banco
    assert User.objects.filter(pk=estudante.pk).exists()
    assert Challenge.objects.filter(pk=desafio_aberto.pk).exists()


@pytest.mark.django_db
def test_seedDemo_registraORaioXDeCadaEntrega(senha_definida):
    call_command("seed_demo")

    assert RepoSnapshot.objects.count() == Submission.objects.count()
    for snapshot in RepoSnapshot.objects.select_related("submission"):
        assert snapshot.status == RepoSnapshot.Status.READY
        assert len(snapshot.commit_sha) == 40
        assert snapshot.main_language
        assert snapshot.registered_late is False
