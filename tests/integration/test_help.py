"""
Ajuda do sistema: a página pública com o passo a passo de cada perfil e o manual em PDF.

Fluxo exercitado: django.test.Client -> middlewares -> core.views.help_page -> template.
Nada é simulado.
"""
import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

MANUAL = "core/manual-do-sistema-devstage.pdf"


@pytest.fixture(autouse=True)
def estaticos_sem_manifesto(settings):
    # Em produção os estáticos passam pelo collectstatic; no teste, a página usa os arquivos direto
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.mark.django_db
def test_visitante_abre_a_ajuda_com_as_secoes_de_cada_perfil(client):
    response = client.get(reverse("core:help"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Como usar o DevStage" in html
    for ancora in ["primeiros-passos", "estudante", "empresa", "administrador", "ranking", "meus-dados", "mensagens"]:
        assert f'id="{ancora}"' in html
    assert MANUAL in html


def test_manual_em_pdf_acompanha_o_sistema():
    # O link da ajuda aponta para um arquivo estático: se ele sumir, o link quebra em produção
    caminho = finders.find(MANUAL)

    assert caminho is not None
    with open(caminho, "rb") as arquivo:
        assert arquivo.read(5) == b"%PDF-"


@pytest.mark.django_db
def test_tela_de_entrada_tem_o_link_da_ajuda_no_rodape(client):
    response = client.get(reverse("login"))

    assert f'href="{reverse("core:help")}"' in response.content.decode()


@pytest.mark.django_db
def test_link_do_menu_abre_a_ajuda_na_parte_do_perfil(client, estudante, empresa):
    ajuda = reverse("core:help")

    client.force_login(estudante)
    assert f'href="{ajuda}#estudante"' in client.get(ajuda).content.decode()

    client.force_login(empresa.user)
    assert f'href="{ajuda}#empresa"' in client.get(ajuda).content.decode()


@pytest.mark.django_db
def test_ajuda_continua_aberta_para_quem_ainda_nao_aceitou_os_termos(client, estudante, monkeypatch):
    # Sem aceite da versão vigente, a navegação é barrada, mas ler a ajuda continua permitido
    monkeypatch.setattr("accounts.middleware.has_current_consent", lambda user: False)
    client.force_login(estudante)

    assert client.get(reverse("challenges:list")).status_code == 302
    assert client.get(reverse("core:help")).status_code == 200
