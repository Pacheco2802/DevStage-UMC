"""
Testes unitários da classe Challenge: peso da dificuldade, prazo, ciclo de vida (RN21)
e liberação da avaliação (RN41). Objetos criados sem .save(): nada aqui toca o banco.
"""
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import patch

import pytest

from challenges.models import Challenge

AGORA = datetime(2026, 11, 20, 12, 0, tzinfo=dt_timezone.utc)
Status = Challenge.Status
Difficulty = Challenge.Difficulty


def _desafio(status=Status.OPEN, deadline=AGORA + timedelta(days=7), difficulty=Difficulty.BEGINNER):
    return Challenge(title="API de pedidos", status=status, deadline=deadline, difficulty=difficulty)


@pytest.mark.parametrize("difficulty, peso", [
    [Difficulty.BEGINNER, 1],
    [Difficulty.INTERMEDIATE, 2],
    [Difficulty.ADVANCED, 3],
])
def test_weight_deveSeguirONivelDeDificuldade(difficulty, peso):
    assert _desafio(difficulty=difficulty).weight == peso


def test_desafioNovo_deveComecarComoRascunhoIniciante():
    challenge = Challenge(title="Novo")

    assert challenge.status == Status.DRAFT
    assert challenge.difficulty == Difficulty.BEGINNER


def test_str_deveSerOTitulo():
    assert str(_desafio()) == "API de pedidos"


@pytest.mark.parametrize("deadline, vencido", [
    [AGORA + timedelta(seconds=1), False],
    [AGORA, False],  # fronteira: no instante exato do prazo ainda vale
    [AGORA - timedelta(seconds=1), True],
])
@patch("challenges.models.timezone.now", return_value=AGORA)
def test_deadlinePassed_deveCompararOPrazoComOInstanteAtual(_now, deadline, vencido):
    assert _desafio(deadline=deadline).deadline_passed is vencido


@pytest.mark.parametrize("atual, nova, permitido", [
    [Status.DRAFT, Status.OPEN, True],      # publicar
    [Status.OPEN, Status.CLOSED, True],     # encerrar
    [Status.DRAFT, Status.CLOSED, False],   # pular etapa
    [Status.OPEN, Status.DRAFT, False],     # voltar para rascunho
    [Status.CLOSED, Status.OPEN, False],    # reabrir: Encerrado é final
    [Status.CLOSED, Status.DRAFT, False],
    [Status.OPEN, Status.OPEN, False],      # ficar onde está não é transição
])
def test_canTransitionTo_deveSeguirOCicloDeVida(atual, nova, permitido):
    assert _desafio(status=atual).can_transition_to(nova) is permitido


def test_isEditable_rascunho_deveSerEditavelSemConsultarSubmissoes():
    # Sem pk e sem banco: se a regra consultasse as submissões aqui, o teste falharia
    assert _desafio(status=Status.DRAFT).is_editable is True


def test_isEditable_encerrado_nuncaEEditavel():
    assert _desafio(status=Status.CLOSED).is_editable is False


@pytest.mark.parametrize("status, deadline, liberada", [
    [Status.OPEN, AGORA + timedelta(days=1), False],    # ainda cabem entregas
    [Status.OPEN, AGORA - timedelta(seconds=1), True],  # prazo vencido
    [Status.CLOSED, AGORA + timedelta(days=1), True],   # encerrado pela empresa antes do prazo
    [Status.DRAFT, AGORA + timedelta(days=1), False],
])
@patch("challenges.models.timezone.now", return_value=AGORA)
def test_acceptsEvaluation_soDepoisDoPrazoOuDoEncerramento(_now, status, deadline, liberada):
    assert _desafio(status=status, deadline=deadline).accepts_evaluation is liberada
