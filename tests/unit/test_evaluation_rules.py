"""
Testes unitários da avaliação: cálculo dos pontos (classe Evaluation, RF13), validação do
formulário (EvaluationForm, RN42 e RN43) e condições para avaliar (RN41 e RN44).

Nenhum teste aqui toca o banco. Por isso o formulário é testado campo a campo, e não com
is_valid(): a validação completa de um ModelForm confere as restrições do modelo com uma
consulta ao banco, e esse caminho inteiro é coberto em tests/integration/test_evaluation.py.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from challenges.forms import EvaluationForm
from challenges.models import Challenge, Evaluation
from challenges.views import ALREADY_EVALUATED, _check_can_evaluate

AGORA = datetime(2026, 11, 20, 12, 0, tzinfo=dt_timezone.utc)
TEXTO = "Um texto de feedback com mais de vinte caracteres."


# ---------- Evaluation.calculate_points (RN45) ----------

@pytest.mark.parametrize("nota, peso, pontos", [
    [80, 1, 80],
    [80, 2, 160],
    [100, 3, 300],  # maior pontuação possível
    [0, 3, 0],      # nota zero vale zero em qualquer dificuldade
    [1, 1, 1],
])
def test_calculatePoints_deveMultiplicarANotaPeloPeso(nota, peso, pontos):
    assert Evaluation(score=nota, weight=peso).calculate_points() == pontos


def test_minFeedbackLength_deveSerVinteCaracteres():
    assert Evaluation.MIN_FEEDBACK_LENGTH == 20


# ---------- EvaluationForm: nota (RN42) ----------

def _campo_nota():
    return EvaluationForm().fields["score"]


@pytest.mark.parametrize("nota", [0, 1, 50, 99, 100, "85"])
def test_form_notaDentroDaFaixa_deveSerAceitaComoInteiro(nota):
    assert _campo_nota().clean(nota) == int(nota)


@pytest.mark.parametrize("nota", [-1, 101, 1000, "", None, "abc", "8.5"])
def test_form_notaForaDaFaixaOuNaoInteira_deveSerRecusada(nota):
    with pytest.raises(ValidationError):
        _campo_nota().clean(nota)


def test_form_deveTerSoNotaEAsDuasPartesDoFeedback():
    # Peso e pontos são calculados pelo sistema e não existem como campos: não há como digitá-los
    assert list(EvaluationForm().fields) == ["score", "strengths", "improvements"]


def test_form_asDuasPartesDoFeedbackSaoObrigatorias():
    form = EvaluationForm()

    assert form.fields["strengths"].required is True
    assert form.fields["improvements"].required is True


# ---------- EvaluationForm: feedback (RN43) ----------

def _limpar(campo, texto):
    """Roda só a regra do campo, como o Django faz depois de ler o valor enviado."""
    form = EvaluationForm()
    form.cleaned_data = {campo: texto}
    return getattr(form, f"clean_{campo}")()


@pytest.mark.parametrize("campo", ["strengths", "improvements"])
@pytest.mark.parametrize("texto", ["curto", "x" * 19, " " * 30, "  dezenove letras..  "])
def test_form_feedbackComMenosDe20Caracteres_deveSerRecusado(campo, texto):
    with pytest.raises(ValidationError) as erro:
        _limpar(campo, texto)

    assert erro.value.messages == ["Escreva pelo menos 20 caracteres."]


@pytest.mark.parametrize("campo", ["strengths", "improvements"])
def test_form_feedbackDeExatamente20Caracteres_deveSerAceito(campo):
    assert _limpar(campo, "x" * 20) == "x" * 20


def test_form_deveRemoverEspacosDasPontasDoFeedback():
    assert _limpar("strengths", f"   {TEXTO}   ") == TEXTO


# ---------- _check_can_evaluate (RN41 e RN44) ----------

def _desafio(status=Challenge.Status.OPEN, deadline=AGORA - timedelta(days=1)):
    return Challenge(title="API de pedidos", status=status, deadline=deadline)


@patch("challenges.models.timezone.now", return_value=AGORA)
def test_checkCanEvaluate_comPrazoVencidoESemAvaliacao_deveLiberar(_now):
    assert _check_can_evaluate(_desafio(), existing_evaluation=None) == ""


@patch("challenges.models.timezone.now", return_value=AGORA)
def test_checkCanEvaluate_comPrazoEmAndamento_deveBloquear(_now):
    motivo = _check_can_evaluate(_desafio(deadline=AGORA + timedelta(days=1)), existing_evaluation=None)

    assert motivo == "A avaliação só é liberada depois do prazo ou do encerramento do desafio."


@patch("challenges.models.timezone.now", return_value=AGORA)
def test_checkCanEvaluate_comAvaliacaoExistente_deveBloquear(_now):
    assert _check_can_evaluate(_desafio(), existing_evaluation=Evaluation()) == ALREADY_EVALUATED


@patch("challenges.models.timezone.now", return_value=AGORA)
def test_checkCanEvaluate_deveInformarPrimeiroQueJaFoiAvaliada(_now):
    # As duas condições falham ao mesmo tempo: a mensagem é a da avaliação já existente
    motivo = _check_can_evaluate(_desafio(deadline=AGORA + timedelta(days=1)), existing_evaluation=Evaluation())

    assert motivo == ALREADY_EVALUATED
