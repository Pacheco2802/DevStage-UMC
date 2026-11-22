"""
Testes unitários do ChallengeForm (RN19 e RN20) e do validador do usuário do GitHub do
StudentProfile. Nenhum teste aqui toca o banco.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from accounts.models import StudentProfile
from challenges.forms import ChallengeForm
from challenges.models import Challenge

AGORA = datetime(2026, 11, 20, 12, 0, tzinfo=dt_timezone.utc)


def _dados(**mudancas):
    dados = {
        "title": "Encurtador de links", "description": "Crie um encurtador de URLs.",
        "difficulty": Challenge.Difficulty.ADVANCED, "deadline": "2026-12-01T18:00",
        "status": Challenge.Status.DRAFT,
    }
    dados.update(mudancas)
    return dados


@patch("challenges.forms.timezone.now", return_value=AGORA)
def test_form_comDadosValidos_deveSerValido(_now):
    assert ChallengeForm(_dados()).is_valid()


@pytest.mark.parametrize("prazo", ["2026-11-20T08:59", "2026-11-19T23:00", "2020-01-01T00:00"])
@patch("challenges.forms.timezone.now", return_value=AGORA)
def test_form_comPrazoNoPassado_deveApontarErroNoPrazo(_now, prazo):
    # AGORA é 12:00 UTC, ou seja, 09:00 em São Paulo
    form = ChallengeForm(_dados(deadline=prazo))

    assert not form.is_valid()
    assert form.errors["deadline"] == ["O prazo precisa ser uma data futura."]


@patch("challenges.forms.timezone.now", return_value=AGORA)
def test_form_comPrazoIgualAoInstanteAtual_deveRecusar(_now):
    assert not ChallengeForm(_dados(deadline="2026-11-20T09:00")).is_valid()


@patch("challenges.forms.timezone.now", return_value=AGORA)
def test_form_naCriacao_naoAceitaSituacaoEncerrado(_now):
    form = ChallengeForm(_dados(status=Challenge.Status.CLOSED))

    assert not form.is_valid()
    assert "status" in form.errors


@patch("challenges.forms.timezone.now", return_value=AGORA)
def test_form_comDificuldadeInexistente_deveApontarErro(_now):
    form = ChallengeForm(_dados(difficulty="IMPOSSIVEL"))

    assert not form.is_valid()
    assert "difficulty" in form.errors


@pytest.mark.parametrize("campo", ["title", "description", "difficulty", "deadline", "status"])
@patch("challenges.forms.timezone.now", return_value=AGORA)
def test_form_semCampoObrigatorio_deveApontarErroNoCampo(_now, campo):
    form = ChallengeForm(_dados(**{campo: ""}))

    assert not form.is_valid()
    assert campo in form.errors


def test_form_naEdicao_naoTemOCampoDeSituacao():
    existente = Challenge(pk=1, title="Existente", deadline=AGORA + timedelta(days=3))

    form = ChallengeForm(instance=existente)

    assert "status" not in form.fields
    assert list(form.fields) == ["title", "description", "difficulty", "deadline"]


# ---------- StudentProfile.github_username ----------

def _validar_github(valor):
    StudentProfile._meta.get_field("github_username").run_validators(valor)


@pytest.mark.parametrize("valor", ["pedro", "pedro-pacheco", "Pacheco2802", "a", "a1-b2-c3"])
def test_githubUsername_valido_devePassar(valor):
    _validar_github(valor)


@pytest.mark.parametrize("valor", ["@pedro", "https://github.com/pedro", "pedro pacheco", "-pedro", "pedro-", "pedro/repo"])
def test_githubUsername_invalido_deveSerRecusado(valor):
    with pytest.raises(ValidationError):
        _validar_github(valor)


def test_perfilNovo_deveNascerComPortfolioPublico():
    assert StudentProfile().portfolio_public is True
