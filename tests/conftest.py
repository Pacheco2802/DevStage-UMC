import pytest


@pytest.fixture(autouse=True)
def sem_token_do_github(settings):
    """Os testes não dependem do GITHUB_TOKEN que estiver no .env de quem os roda."""
    settings.GITHUB_TOKEN = ""


@pytest.fixture(autouse=True)
def senhas_rapidas(settings):
    """O hash de produção (PBKDF2 com 1.000.000 de iterações) é lento de propósito. Como quase
    todo teste cria usuários, aqui vale um hash rápido; a regra de senha em si não muda."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
