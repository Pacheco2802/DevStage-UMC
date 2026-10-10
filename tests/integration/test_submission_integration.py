from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from challenges.models import Submission
from integrations.github_client import GitHubValidationResult

DADOS_ENTREGA = {
    "repo_url": "https://github.com/aluno/api-pedidos",
    "deploy_url": "",
    "description": "Usei Django REST e Postgres.",
}


@pytest.mark.django_db
def test_deve_retornar_200_com_dados_do_desafio_para_estudante_logado(client, estudante, desafio_aberto):
    # Arrange
    client.force_login(estudante)

    # Act
    response = client.get(reverse("challenges:detail", args=[desafio_aberto.pk]))

    # Assert
    assert response.status_code == 200
    body = response.content.decode()
    assert "API de pedidos" in body
    assert "Acme Tech" in body


@pytest.mark.django_db
def test_deve_retornar_404_quando_desafio_nao_existe(client, estudante):
    # Arrange
    client.force_login(estudante)

    # Act
    response = client.get(reverse("challenges:detail", args=[999999]))

    # Assert
    assert response.status_code == 404
    assert "Not Found" in response.content.decode()


@pytest.mark.django_db
def test_deve_salvar_submissao_e_bloquear_duplicata_no_banco(estudante, desafio_aberto):
    # Arrange
    Submission.objects.create(challenge=desafio_aberto, student=estudante, **DADOS_ENTREGA)

    # Act / Assert: a primeira foi persistida e pode ser recuperada
    salva = Submission.objects.get(challenge=desafio_aberto, student=estudante)
    assert salva.repo_url == DADOS_ENTREGA["repo_url"]

    # Act / Assert: a segunda viola o UniqueConstraint do banco
    with pytest.raises(IntegrityError), transaction.atomic():
        Submission.objects.create(challenge=desafio_aberto, student=estudante, **DADOS_ENTREGA)
    assert Submission.objects.filter(challenge=desafio_aberto, student=estudante).count() == 1


@pytest.mark.django_db
@patch("challenges.forms.repo_exists", return_value=GitHubValidationResult(False, "Repositório não encontrado no GitHub."))
def test_deve_reexibir_formulario_com_erro_e_nao_gravar_quando_repositorio_nao_existe(
    _mock_repo_exists, client, estudante, desafio_aberto
):
    # Arrange
    client.force_login(estudante)

    # Act
    response = client.post(reverse("challenges:detail", args=[desafio_aberto.pk]), DADOS_ENTREGA)

    # Assert
    assert response.status_code == 200
    assert "Repositório não encontrado no GitHub." in response.content.decode()
    assert not Submission.objects.exists()


@pytest.mark.django_db
@patch("challenges.forms.repo_exists", return_value=GitHubValidationResult(True))
def test_fluxo_completo_estudante_envia_entrega_e_ve_a_submissao_registrada(
    mock_repo_exists, client, estudante, desafio_aberto
):
    # Arrange
    client.force_login(estudante)
    url = reverse("challenges:detail", args=[desafio_aberto.pk])

    # Act: envia a entrega (view -> form -> model -> banco)
    post_response = client.post(url, DADOS_ENTREGA)

    # Assert: redireciona e grava no banco
    assert post_response.status_code == 302
    assert post_response.url == url
    mock_repo_exists.assert_called_once_with(DADOS_ENTREGA["repo_url"])
    submission = Submission.objects.get(challenge=desafio_aberto, student=estudante)
    assert submission.description == DADOS_ENTREGA["description"]

    # Act: consulta a página do desafio depois da entrega
    get_response = client.get(url)

    # Assert: mensagem de sucesso e a entrega aparecem na página
    body = get_response.content.decode()
    assert get_response.status_code == 200
    assert "Entrega registrada com sucesso!" in body
    assert "Você já enviou uma solução para este desafio" in body
    assert DADOS_ENTREGA["repo_url"] in body
