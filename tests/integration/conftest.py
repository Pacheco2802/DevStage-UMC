from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import CompanyProfile, User
from challenges.models import Challenge

# Cada teste monta o próprio cenário no banco de teste (criado e apagado pelo pytest-django)


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
