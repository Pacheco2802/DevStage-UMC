from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import CompanyProfile, User
from challenges.models import Challenge
from integrations.github_client import RepoDownloadError

# Cada teste monta o próprio cenário no banco de teste (criado e apagado pelo pytest-django)


@pytest.fixture(autouse=True)
def aceite_em_dia(monkeypatch):
    """Os usuários destes testes são criados direto no banco, sem passar pelo cadastro, e por isso
    não têm aceite dos termos. Como o assunto aqui é outra regra, o middleware os trata como em dia.
    A regra do aceite é testada de verdade em test_termos.py, que desliga este atalho."""
    monkeypatch.setattr("accounts.middleware.has_current_consent", lambda user: True)


@pytest.fixture(autouse=True)
def github_sem_rede(monkeypatch):
    """Nenhum teste consulta o GitHub de verdade. Por padrão ele "não responde", que é o caminho
    em que a entrega é aceita sem o commit registrado; test_snapshot.py simula as respostas."""
    def fora_do_ar(*args, **kwargs):
        raise RepoDownloadError("GitHub desligado nos testes")

    monkeypatch.setattr("challenges.services.list_commits", fora_do_ar)
    monkeypatch.setattr("challenges.services.download_repo", fora_do_ar)


@pytest.fixture
def estudante(db):
    return User.objects.create_user(username="aluno", password="senha-teste-123", role=User.Role.STUDENT)


@pytest.fixture
def empresa(db):
    user = User.objects.create_user(username="empresa", password="senha-teste-123", role=User.Role.COMPANY)
    return CompanyProfile.objects.create(user=user, company_name="Acme Tech", approved=True)


@pytest.fixture
def desafio_aberto(empresa):
    return Challenge.objects.create(
        company=empresa,
        title="API de pedidos",
        description="Construa uma API REST de pedidos.",
        deadline=timezone.now() + timedelta(days=7),
        status=Challenge.Status.OPEN,
    )
