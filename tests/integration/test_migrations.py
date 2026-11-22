"""
Testes das migrações de dados da entrega final. Elas rodam sobre o banco de produção, que já
tem avaliações na escala antiga (0 a 10) e estudantes cadastrados antes do portfólio público.

Cada teste volta o esquema para antes da migração, grava dados no formato antigo, aplica a
migração e confere o resultado.
"""
from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

ANTES = [("accounts", "0007_publica_termos_1_2"), ("challenges", "0004_reposnapshot")]


def _migrar(alvos):
    executor = MigrationExecutor(connection)
    executor.migrate(alvos)
    # Um executor novo relê o estado do banco e devolve os modelos como eram naquele ponto
    return MigrationExecutor(connection).loader.project_state(alvos).apps


def _migrar_ate_o_fim():
    executor = MigrationExecutor(connection)
    alvos = executor.loader.graph.leaf_nodes()
    executor.migrate(alvos)
    return MigrationExecutor(connection).loader.project_state(alvos).apps


@pytest.fixture
def esquema_antigo(transactional_db):
    apps = _migrar(ANTES)
    yield apps
    _migrar_ate_o_fim()  # mesmo que o teste falhe, os próximos encontram o esquema atual


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_migracao_converteAvaliacoesAntigasParaAEscalaDe0a100(esquema_antigo):
    User = esquema_antigo.get_model("accounts", "User")
    CompanyProfile = esquema_antigo.get_model("accounts", "CompanyProfile")
    Challenge = esquema_antigo.get_model("challenges", "Challenge")
    Submission = esquema_antigo.get_model("challenges", "Submission")
    Evaluation = esquema_antigo.get_model("challenges", "Evaluation")

    empresa = CompanyProfile.objects.create(
        user=User.objects.create(username="empresa-antiga", role="COMPANY"), company_name="Antiga", approved=True,
    )
    desafio = Challenge.objects.create(
        company=empresa, title="Desafio antigo", description="x",
        deadline=timezone.now() + timedelta(days=1), status="OPEN",
    )
    for username, nota in [["aluna-antiga", 8], ["aluno-nota-dez", 10], ["aluno-nota-zero", 0]]:
        submissao = Submission.objects.create(
            challenge=desafio, student=User.objects.create(username=username, role="STUDENT"),
            repo_url="https://github.com/a/b", description="x",
        )
        Evaluation.objects.create(submission=submissao, score=nota, feedback=f"Feedback antigo de {username}.")

    apps = _migrar_ate_o_fim()

    Evaluation = apps.get_model("challenges", "Evaluation")
    convertidas = {
        avaliacao.submission.student.username: avaliacao
        for avaliacao in Evaluation.objects.select_related("submission__student")
    }
    assert convertidas["aluna-antiga"].score == 80
    assert convertidas["aluna-antiga"].points == 80          # desafio antigo vira Iniciante, peso 1
    assert convertidas["aluna-antiga"].weight == 1
    assert convertidas["aluna-antiga"].strengths == "Feedback antigo de aluna-antiga."
    assert convertidas["aluna-antiga"].improvements == ""
    assert convertidas["aluno-nota-dez"].score == 100
    assert convertidas["aluno-nota-zero"].points == 0
    assert apps.get_model("challenges", "Challenge").objects.get().difficulty == "BEGINNER"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_migracao_criaPerfilPrivadoParaEstudantesQueJaExistiam(esquema_antigo):
    User = esquema_antigo.get_model("accounts", "User")
    User.objects.create(username="aluna-antiga", role="STUDENT")
    User.objects.create(username="empresa-antiga", role="COMPANY")

    apps = _migrar_ate_o_fim()

    StudentProfile = apps.get_model("accounts", "StudentProfile")
    perfil = StudentProfile.objects.get()  # só o estudante ganha perfil
    assert perfil.user.username == "aluna-antiga"
    assert perfil.portfolio_public is False
