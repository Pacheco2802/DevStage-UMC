from unittest.mock import Mock, patch

import pytest
import requests

from integrations.github_client import parse_repo_url, repo_exists

URL_VALIDA = "https://github.com/pedro/devstage"
API_ESPERADA = "https://api.github.com/repos/pedro/devstage"


def _resposta(status_code):
    return Mock(status_code=status_code)


@patch("integrations.github_client.requests.get")
def test_deve_validar_repositorio_quando_github_responde_200(mock_get):
    # Arrange
    mock_get.return_value = _resposta(200)

    # Act
    result = repo_exists(URL_VALIDA)

    # Assert
    assert result.valid is True
    assert result.reason == ""
    mock_get.assert_called_once_with(
        API_ESPERADA,
        timeout=3,
        headers={"Accept": "application/vnd.github+json"},
    )


@patch("integrations.github_client.requests.get")
def test_deve_invalidar_repositorio_quando_github_responde_404(mock_get):
    # Arrange
    mock_get.return_value = _resposta(404)

    # Act
    result = repo_exists(URL_VALIDA)

    # Assert
    assert result.valid is False
    assert result.reason == "Repositório não encontrado no GitHub."


@patch("integrations.github_client.requests.get")
def test_deve_invalidar_url_fora_do_github_sem_chamar_a_api(mock_get):
    # Act
    result = repo_exists("https://gitlab.com/pedro/devstage")

    # Assert
    assert result.valid is False
    assert result.reason == "URL não tem formato de repositório GitHub válido."
    mock_get.assert_not_called()


@patch("integrations.github_client.requests.get")
def test_deve_aceitar_pelo_formato_quando_api_do_github_esta_fora_do_ar(mock_get):
    # Arrange
    mock_get.side_effect = requests.Timeout()

    # Act
    result = repo_exists(URL_VALIDA)

    # Assert
    assert result.valid is True
    assert result.reason == "API do GitHub indisponível; validado apenas pelo formato."


@patch("integrations.github_client.requests.get")
def test_deve_aceitar_pelo_formato_quando_github_retorna_rate_limit_403(mock_get):
    # Arrange
    mock_get.return_value = _resposta(403)

    # Act
    result = repo_exists(URL_VALIDA)

    # Assert
    assert result.valid is True
    assert result.reason == "GitHub respondeu 403; validado pelo formato."


@pytest.mark.parametrize(
    "url, esperado",
    [
        ("https://github.com/pedro/devstage", ("pedro", "devstage")),
        ("https://github.com/pedro/devstage.git", ("pedro", "devstage")),
        ("https://github.com/pedro/devstage/", ("pedro", "devstage")),
        ("HTTPS://GITHUB.COM/pedro/devstage", ("pedro", "devstage")),
        ("  https://github.com/pedro/devstage  ", ("pedro", "devstage")),
        ("https://github.com/pedro", (None, None)),
        ("https://github.com/pedro/devstage/tree/main", (None, None)),
    ],
    ids=["simples", "sufixo-git", "barra-final", "maiusculas", "espacos", "sem-repo", "subcaminho"],
)
def test_deve_extrair_dono_e_repositorio_nas_variacoes_de_formato_da_url(url, esperado):
    # Act
    resultado = parse_repo_url(url)

    # Assert
    assert resultado == esperado
