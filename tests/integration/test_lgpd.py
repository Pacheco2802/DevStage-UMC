import json

import pytest
from django.conf import settings
from django.urls import reverse

from accounts.models import ConsentLog, User
from audit.models import AuditLog
from challenges.models import Challenge, Submission

SENHA = "Senha-Forte-2026!"


def _dados_cadastro_estudante(**extra):
    dados = {
        "username": "novoaluno",
        "email": "novo@aluno.com",
        "first_name": "Novo",
        "password1": SENHA,
        "password2": SENHA,
        "accept_lgpd": "on",
    }
    dados.update(extra)
    return dados


@pytest.fixture
def consentimento(estudante):
    return ConsentLog.objects.create(
        user=estudante, terms_version=settings.LGPD_TERMS_VERSION, ip="127.0.0.1", user_agent="pytest"
    )


# ---------- Gaps 1-4 e 8: evidência do aceite ----------

@pytest.mark.django_db
def test_cadastro_estudante_grava_consentimento_com_evidencias(client):
    client.post(
        reverse("signup_student"),
        _dados_cadastro_estudante(),
        REMOTE_ADDR="10.0.0.7",
        HTTP_USER_AGENT="Mozilla/5.0 teste",
    )

    user = User.objects.get(username="novoaluno")
    consent = ConsentLog.objects.get(user=user)
    assert consent.terms_version == settings.LGPD_TERMS_VERSION
    assert consent.ip == "10.0.0.7"
    assert consent.user_agent == "Mozilla/5.0 teste"
    assert consent.accepted_at is not None
    assert consent.revoked_at is None


@pytest.mark.django_db
def test_cadastro_empresa_grava_consentimento(client):
    client.post(reverse("signup_company"), {
        "username": "novaempresa",
        "email": "rh@empresa.com",
        "company_name": "Empresa Nova",
        "password1": SENHA,
        "password2": SENHA,
        "accept_lgpd": "on",
    })

    assert ConsentLog.objects.filter(user__username="novaempresa").count() == 1


@pytest.mark.django_db
def test_cadastro_sem_aceite_nao_cria_usuario_nem_consentimento(client):
    dados = _dados_cadastro_estudante()
    del dados["accept_lgpd"]

    response = client.post(reverse("signup_student"), dados)

    assert response.status_code == 200
    assert not User.objects.filter(username="novoaluno").exists()
    assert ConsentLog.objects.count() == 0


# ---------- Gap 5: revogação ----------

@pytest.mark.django_db
def test_revogar_consentimento_desativa_conta_e_desloga(client, estudante, consentimento):
    client.force_login(estudante)

    response = client.post(reverse("revoke_consent"))

    assert response.status_code == 302
    consentimento.refresh_from_db()
    estudante.refresh_from_db()
    assert consentimento.revoked_at is not None
    assert estudante.is_active is False
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_revogar_consentimento_exige_post(client, estudante, consentimento):
    client.force_login(estudante)

    response = client.get(reverse("revoke_consent"))

    assert response.status_code == 405
    consentimento.refresh_from_db()
    assert consentimento.revoked_at is None


# ---------- Gap 6: Meus Dados (acesso, correção, portabilidade, eliminação) ----------

@pytest.mark.django_db
def test_meus_dados_exige_login(client):
    response = client.get(reverse("my_data"))

    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_meus_dados_mostra_historico_de_consentimento(client, estudante, consentimento):
    client.force_login(estudante)

    response = client.get(reverse("my_data"))

    assert response.status_code == 200
    assert consentimento in response.context["consents"]
    assert settings.DPO_EMAIL in response.content.decode()


@pytest.mark.django_db
def test_correcao_de_dados_atualiza_email(client, estudante, consentimento):
    client.force_login(estudante)

    client.post(reverse("my_data"), {"first_name": "Aluno", "last_name": "Teste", "email": "novo@email.com"})

    estudante.refresh_from_db()
    assert estudante.email == "novo@email.com"
    assert estudante.last_name == "Teste"


@pytest.mark.django_db
def test_correcao_com_email_invalido_nao_salva(client, estudante, consentimento):
    estudante.email = "original@email.com"
    estudante.save()
    client.force_login(estudante)

    response = client.post(reverse("my_data"), {"first_name": "", "last_name": "", "email": "nao-e-email"})

    assert response.status_code == 200
    assert "email" in response.context["form"].errors
    estudante.refresh_from_db()
    assert estudante.email == "original@email.com"


@pytest.mark.django_db
def test_exportar_dados_retorna_json_e_registra_auditoria(client, estudante, consentimento, desafio_aberto):
    Submission.objects.create(
        challenge=desafio_aberto, student=estudante,
        repo_url="https://github.com/aluno/api", description="Minha solução",
    )
    client.force_login(estudante)

    response = client.get(reverse("my_data_export"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert "attachment" in response["Content-Disposition"]
    data = json.loads(response.content)
    assert data["usuario"]["username"] == "aluno"
    assert data["consentimentos"][0]["versao_termos"] == settings.LGPD_TERMS_VERSION
    assert data["submissoes"][0]["repo_url"] == "https://github.com/aluno/api"
    assert AuditLog.objects.filter(user=estudante, action=AuditLog.Action.ACCESS).exists()


@pytest.mark.django_db
def test_excluir_conta_com_confirmacao_errada_nao_anonimiza(client, estudante, consentimento):
    client.force_login(estudante)

    client.post(reverse("my_data_delete"), {"confirm_username": "outro-nome"})

    estudante.refresh_from_db()
    assert estudante.username == "aluno"
    assert estudante.is_active is True


@pytest.mark.django_db
def test_excluir_conta_anonimiza_e_preserva_submissoes(client, estudante, consentimento, desafio_aberto):
    estudante.email = "aluno@email.com"
    estudante.first_name = "Fulano"
    estudante.save()
    Submission.objects.create(
        challenge=desafio_aberto, student=estudante,
        repo_url="https://github.com/aluno/api", description="Minha solução",
    )
    client.force_login(estudante)

    client.post(reverse("my_data_delete"), {"confirm_username": "aluno"})

    estudante.refresh_from_db()
    consentimento.refresh_from_db()
    assert estudante.username == f"removido-{estudante.pk}"
    assert estudante.email == ""
    assert estudante.first_name == ""
    assert estudante.is_active is False
    assert not estudante.has_usable_password()
    assert consentimento.revoked_at is not None
    assert Submission.objects.filter(student=estudante).count() == 1
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_excluir_conta_de_empresa_encerra_desafios_abertos(client, empresa, desafio_aberto):
    client.force_login(empresa.user)

    client.post(reverse("my_data_delete"), {"confirm_username": "empresa"})

    desafio_aberto.refresh_from_db()
    empresa.refresh_from_db()
    assert desafio_aberto.status == Challenge.Status.CLOSED
    assert empresa.company_name == f"Empresa removida #{empresa.pk}"


# ---------- Gap 7: encarregado (DPO) ----------

@pytest.mark.django_db
def test_politica_de_privacidade_exibe_contato_do_dpo(client):
    response = client.get(reverse("core:privacy"))

    content = response.content.decode()
    assert settings.DPO_EMAIL in content
    assert settings.DPO_NAME in content
