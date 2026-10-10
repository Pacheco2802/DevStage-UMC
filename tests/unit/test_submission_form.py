from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from challenges.forms import SubmissionForm
from integrations.github_client import GitHubValidationResult

URL = "https://github.com/pedro/devstage"


def _form_com_repo_url(url):
    # Chama clean_repo_url() isolado, sem passar pelo is_valid() (que valida o model inteiro)
    form = SubmissionForm()
    form.cleaned_data = {"repo_url": url}
    return form


# O patch é em challenges.forms, porque é lá que o nome repo_exists é usado
@patch("challenges.forms.repo_exists")
def test_deve_aceitar_repo_url_quando_repositorio_existe(mock_repo_exists):
    # Arrange
    mock_repo_exists.return_value = GitHubValidationResult(True)
    form = _form_com_repo_url(URL)

    # Act
    cleaned = form.clean_repo_url()

    # Assert
    assert cleaned == URL
    mock_repo_exists.assert_called_once_with(URL)


@patch("challenges.forms.repo_exists")
def test_deve_lancar_validation_error_quando_repositorio_nao_existe(mock_repo_exists):
    # Arrange
    mock_repo_exists.return_value = GitHubValidationResult(False, "Repositório não encontrado no GitHub.")
    form = _form_com_repo_url(URL)

    # Act / Assert
    with pytest.raises(ValidationError) as exc:
        form.clean_repo_url()
    assert exc.value.messages == ["Repositório não encontrado no GitHub."]


@patch("challenges.forms.repo_exists")
def test_deve_lancar_validation_error_quando_url_nao_e_do_github(mock_repo_exists):
    # Arrange
    mock_repo_exists.return_value = GitHubValidationResult(
        False, "URL não tem formato de repositório GitHub válido."
    )
    form = _form_com_repo_url("https://gitlab.com/pedro/devstage")

    # Act / Assert
    with pytest.raises(ValidationError) as exc:
        form.clean_repo_url()
    assert exc.value.messages == ["URL não tem formato de repositório GitHub válido."]


@patch("challenges.forms.repo_exists")
def test_deve_aceitar_repo_url_quando_github_indisponivel_e_formato_valido(mock_repo_exists):
    # Arrange: fallback — validação passou só pelo formato, com motivo preenchido
    mock_repo_exists.return_value = GitHubValidationResult(
        True, "API do GitHub indisponível; validado apenas pelo formato."
    )
    form = _form_com_repo_url(URL)

    # Act
    cleaned = form.clean_repo_url()

    # Assert
    assert cleaned == URL
