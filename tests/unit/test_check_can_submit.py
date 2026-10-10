from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

import pytest

from accounts.models import User
from challenges.models import Challenge, Submission
from challenges.views import _check_can_submit

# Instante fixo para os testes não dependerem do relógio da máquina
AGORA = datetime(2026, 10, 9, 12, 0, tzinfo=dt_timezone.utc)

# Objetos criados sem .save(): nada aqui toca o banco


def _estudante():
    return User(username="aluno", role=User.Role.STUDENT)


def _desafio(status=Challenge.Status.OPEN, deadline=AGORA + timedelta(days=7)):
    return Challenge(title="API de pedidos", status=status, deadline=deadline)


@patch("challenges.views.timezone.now", return_value=AGORA)
def test_deve_permitir_submissao_quando_estudante_desafio_aberto_e_no_prazo(_now):
    # Arrange
    user = _estudante()
    challenge = _desafio()

    # Act
    can_submit, reason = _check_can_submit(challenge, user, existing_submission=None)

    # Assert
    assert can_submit is True
    assert reason == ""


@pytest.mark.parametrize(
    "role, status, deadline, ja_submeteu, mensagem_esperada",
    [
        (User.Role.COMPANY, Challenge.Status.OPEN, AGORA + timedelta(days=1), False,
         "Apenas usuários com perfil de estudante podem submeter."),
        (User.Role.STUDENT, Challenge.Status.DRAFT, AGORA + timedelta(days=1), False,
         "Este desafio não está aberto para submissões."),
        (User.Role.STUDENT, Challenge.Status.CLOSED, AGORA + timedelta(days=1), False,
         "Este desafio não está aberto para submissões."),
        (User.Role.STUDENT, Challenge.Status.OPEN, AGORA - timedelta(seconds=1), False,
         "O prazo deste desafio já venceu."),
        (User.Role.STUDENT, Challenge.Status.OPEN, AGORA + timedelta(days=1), True,
         "Você já enviou uma submissão para este desafio."),
    ],
    ids=["perfil-empresa", "status-rascunho", "status-encerrado", "prazo-vencido", "submissao-duplicada"],
)
@patch("challenges.views.timezone.now", return_value=AGORA)
def test_deve_bloquear_submissao_com_a_mensagem_da_regra_violada(
    _now, role, status, deadline, ja_submeteu, mensagem_esperada
):
    # Arrange
    user = User(username="usuario", role=role)
    challenge = _desafio(status=status, deadline=deadline)
    existing = Submission() if ja_submeteu else None

    # Act
    can_submit, reason = _check_can_submit(challenge, user, existing)

    # Assert
    assert can_submit is False
    assert reason == mensagem_esperada


@patch("challenges.views.timezone.now", return_value=AGORA)
def test_deve_permitir_submissao_quando_prazo_termina_exatamente_agora(_now):
    # Arrange: deadline igual ao instante atual (fronteira da regra "deadline < agora")
    user = _estudante()
    challenge = _desafio(deadline=AGORA)

    # Act
    can_submit, reason = _check_can_submit(challenge, user, existing_submission=None)

    # Assert
    assert can_submit is True
    assert reason == ""


@patch("challenges.views.timezone.now", return_value=AGORA)
def test_deve_priorizar_bloqueio_de_perfil_quando_todas_as_regras_sao_violadas(_now):
    # Arrange: empresa, desafio encerrado, prazo vencido e submissão existente ao mesmo tempo
    user = User(username="empresa", role=User.Role.COMPANY)
    challenge = _desafio(status=Challenge.Status.CLOSED, deadline=AGORA - timedelta(days=1))

    # Act
    can_submit, reason = _check_can_submit(challenge, user, Submission())

    # Assert
    assert can_submit is False
    assert reason == "Apenas usuários com perfil de estudante podem submeter."
