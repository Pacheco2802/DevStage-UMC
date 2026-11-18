"""
Versionamento dos termos (LGPD art. 8º, § 6º): publicar uma versão nova exige novo aceite.

Fluxo exercitado: django.test.Client -> TermsConsentMiddleware -> views de aceite e dos
documentos -> PostgreSQL de teste. Nada é simulado.
"""
import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import ConsentLog, TermsVersion, User

SENHA = "Senha-Forte-2026!"


@pytest.fixture(autouse=True)
def aceite_em_dia():
    """Aqui o aceite é o próprio assunto: desliga o atalho do conftest e vale a regra real."""


@pytest.fixture
def versao_nova(db):
    # Publicada "agora": passa a ser a vigente, à frente das versões criadas pelas migrações
    return TermsVersion.objects.create(
        version="9.9",
        published_at=timezone.now(),
        summary="Item 3: mudou a regra de teste.",
    )


def _aceitar(user, versao, **extra):
    return ConsentLog.objects.create(user=user, terms_version=versao, **extra)


# ---------- Quem precisa aceitar ----------

@pytest.mark.django_db
def test_aceite_de_versao_antiga_leva_a_tela_de_aceite(client, estudante, versao_nova):
    _aceitar(estudante, "1.0")
    client.force_login(estudante)

    response = client.get(reverse("challenges:list"))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("terms_accept")


@pytest.mark.django_db
def test_aceite_da_versao_vigente_navega_normalmente(client, estudante, versao_nova):
    _aceitar(estudante, "9.9")
    client.force_login(estudante)

    response = client.get(reverse("challenges:list"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_conta_sem_nenhum_aceite_tambem_precisa_aceitar(client, estudante, versao_nova):
    # Conta criada fora do cadastro (admin, createsuperuser) nunca consentiu
    client.force_login(estudante)

    response = client.get(reverse("challenges:list"))

    assert response.headers.get("Location") == reverse("terms_accept")


@pytest.mark.django_db
def test_aceite_revogado_nao_vale_como_aceite(client, estudante, versao_nova):
    # Conta reativada pelo encarregado depois de uma revogação: precisa consentir de novo
    _aceitar(estudante, "9.9", revoked_at=timezone.now())
    client.force_login(estudante)

    response = client.get(reverse("challenges:list"))

    assert response.headers.get("Location") == reverse("terms_accept")


@pytest.mark.django_db
def test_visitante_nao_e_levado_a_tela_de_aceite(client, versao_nova):
    response = client.get(reverse("login"))

    assert response.status_code == 200


# ---------- O que continua acessível sem o aceite ----------

@pytest.mark.django_db
@pytest.mark.parametrize("rota", ["my_data", "my_data_export", "terms_accept"])
def test_direitos_do_titular_nao_dependem_do_aceite(client, estudante, versao_nova, rota):
    _aceitar(estudante, "1.0")
    client.force_login(estudante)

    response = client.get(reverse(rota))

    assert response.status_code == 200


@pytest.mark.django_db
def test_recusar_a_versao_nova_revoga_o_consentimento_e_desativa_a_conta(client, estudante, versao_nova):
    aceite_antigo = _aceitar(estudante, "1.0")
    client.force_login(estudante)

    client.post(reverse("revoke_consent"))

    aceite_antigo.refresh_from_db()
    estudante.refresh_from_db()
    assert aceite_antigo.revoked_at is not None
    assert estudante.is_active is False


@pytest.mark.django_db
def test_sair_funciona_sem_o_aceite(client, estudante, versao_nova):
    client.force_login(estudante)

    client.post(reverse("logout"))

    assert "_auth_user_id" not in client.session


# ---------- Tela de aceite ----------

@pytest.mark.django_db
def test_tela_de_aceite_mostra_a_versao_e_o_resumo_das_mudancas(client, estudante, versao_nova):
    _aceitar(estudante, "1.0")
    client.force_login(estudante)

    response = client.get(reverse("terms_accept"))

    conteudo = response.content.decode()
    assert "9.9" in conteudo
    assert "Item 3: mudou a regra de teste." in conteudo


@pytest.mark.django_db
def test_aceitar_grava_novo_consentimento_e_libera_a_navegacao(client, estudante, versao_nova):
    aceite_antigo = _aceitar(estudante, "1.0")
    client.force_login(estudante)

    client.post(
        reverse("terms_accept"),
        {"accept_lgpd": "on"},
        REMOTE_ADDR="10.0.0.7",
        HTTP_USER_AGENT="Mozilla/5.0 teste",
    )

    novo = ConsentLog.objects.get(user=estudante, terms_version="9.9")
    assert novo.ip == "10.0.0.7"
    assert novo.user_agent == "Mozilla/5.0 teste"
    assert novo.revoked_at is None
    # O aceite antigo continua no histórico, intacto: é a prova do que valia antes
    aceite_antigo.refresh_from_db()
    assert aceite_antigo.revoked_at is None
    assert client.get(reverse("challenges:list")).status_code == 200


@pytest.mark.django_db
def test_enviar_sem_marcar_o_aceite_nao_grava_consentimento(client, estudante, versao_nova):
    client.force_login(estudante)

    response = client.post(reverse("terms_accept"), {})

    assert response.status_code == 200
    assert not ConsentLog.objects.filter(user=estudante).exists()


@pytest.mark.django_db
def test_quem_ja_aceitou_nao_gera_aceite_duplicado(client, estudante, versao_nova):
    _aceitar(estudante, "9.9")
    client.force_login(estudante)

    client.post(reverse("terms_accept"), {"accept_lgpd": "on"})

    assert ConsentLog.objects.filter(user=estudante, terms_version="9.9").count() == 1


# ---------- Cadastro ----------

@pytest.mark.django_db
def test_cadastro_grava_o_aceite_da_versao_vigente(client, versao_nova):
    client.post(reverse("signup_student"), {
        "username": "novoaluno",
        "email": "novo@aluno.com",
        "first_name": "Novo",
        "password1": SENHA,
        "password2": SENHA,
        "accept_lgpd": "on",
    })

    user = User.objects.get(username="novoaluno")
    assert ConsentLog.objects.get(user=user).terms_version == "9.9"


# ---------- Documentos ----------

@pytest.mark.django_db
@pytest.mark.parametrize("rota", ["core:terms_version", "core:privacy_version"])
def test_toda_versao_publicada_tem_os_dois_documentos(client, rota):
    # Protege o acoplamento linha no banco <-> template: publicar a versão sem o texto quebra aqui
    versoes = list(TermsVersion.objects.values_list("version", flat=True))
    assert "1.0" in versoes

    for versao in versoes:
        response = client.get(reverse(rota, args=[versao]))
        assert response.status_code == 200, f"faltou o documento da versão {versao}"


@pytest.mark.django_db
def test_versao_antiga_continua_legivel_e_avisa_que_foi_substituida(client):
    response = client.get(reverse("core:terms_version", args=["1.0"]))

    conteudo = response.content.decode()
    assert "Versão 1.0" in conteudo
    assert "versão anterior" in conteudo.lower()


@pytest.mark.django_db
def test_pagina_sem_versao_na_url_mostra_a_vigente(client):
    response = client.get(reverse("core:terms"))

    assert response.status_code == 200
    assert "versão anterior" not in response.content.decode().lower()


@pytest.mark.django_db
def test_versao_inexistente_devolve_404(client):
    response = client.get(reverse("core:terms_version", args=["0.0"]))

    assert response.status_code == 404
