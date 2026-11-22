"""
Testes de integração do ciclo de vida do desafio (RF05 e RF06): dificuldade, validação do
prazo, transições de situação e bloqueio de edição depois da primeira entrega.
"""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from challenges.models import Challenge, Submission


def _prazo(dias):
    return (timezone.localtime() + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M")


def _dados(**mudancas):
    dados = {
        "title": "Encurtador de links", "description": "Crie um encurtador de URLs.",
        "difficulty": Challenge.Difficulty.INTERMEDIATE, "deadline": _prazo(10),
        "status": Challenge.Status.OPEN,
    }
    dados.update(mudancas)
    return dados


@pytest.fixture
def rascunho(empresa):
    return Challenge.objects.create(
        company=empresa, title="Lista de tarefas", description="Rascunho.",
        deadline=timezone.now() + timedelta(days=5), status=Challenge.Status.DRAFT,
    )


def _entregar(desafio, estudante):
    return Submission.objects.create(
        challenge=desafio, student=estudante, repo_url="https://github.com/aluno/api", description="Solução",
    )


# ---------- RF05: criação ----------

@pytest.mark.django_db
def test_criar_comDificuldade_deveGravarONivelEscolhido(client, empresa):
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:create"), _dados())

    assert response.status_code == 302
    desafio = Challenge.objects.get(title="Encurtador de links")
    assert desafio.difficulty == Challenge.Difficulty.INTERMEDIATE
    assert desafio.weight == 2


@pytest.mark.django_db
def test_criar_comPrazoNoPassado_deveRecusar(client, empresa):
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:create"), _dados(deadline=_prazo(-1)))

    assert response.status_code == 200
    assert response.context["form"].errors["deadline"] == ["O prazo precisa ser uma data futura."]
    assert not Challenge.objects.exists()


@pytest.mark.django_db
def test_criar_jaEncerrado_deveRecusar(client, empresa):
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:create"), _dados(status=Challenge.Status.CLOSED))

    assert response.status_code == 200
    assert "status" in response.context["form"].errors
    assert not Challenge.objects.exists()


@pytest.mark.django_db
def test_criar_formulario_soOfereceRascunhoEAberto(client, empresa):
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:create"))

    opcoes = [valor for valor, _ in response.context["form"].fields["status"].choices]
    assert opcoes == [Challenge.Status.DRAFT, Challenge.Status.OPEN]


# ---------- RF06: transições (RN21) ----------

@pytest.mark.django_db
def test_publicar_rascunho_deveAbrirEAparecerNaLista(client, empresa, estudante, rascunho):
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:publish", args=[rascunho.pk]))

    assert response.status_code == 302
    rascunho.refresh_from_db()
    assert rascunho.status == Challenge.Status.OPEN
    client.force_login(estudante)
    assert "Lista de tarefas" in client.get(reverse("challenges:list")).content.decode()


@pytest.mark.django_db
def test_publicar_rascunhoComPrazoVencido_deveRecusar(client, empresa, rascunho):
    Challenge.objects.filter(pk=rascunho.pk).update(deadline=timezone.now() - timedelta(days=1))
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:publish", args=[rascunho.pk]), follow=True)

    rascunho.refresh_from_db()
    assert rascunho.status == Challenge.Status.DRAFT
    assert "O prazo deste desafio já passou." in response.content.decode()


@pytest.mark.django_db
def test_encerrar_desafioAberto_deveEncerrarEPararDeAceitarSubmissoes(client, empresa, estudante, desafio_aberto):
    client.force_login(empresa.user)

    client.post(reverse("challenges:close", args=[desafio_aberto.pk]))

    desafio_aberto.refresh_from_db()
    assert desafio_aberto.status == Challenge.Status.CLOSED
    client.force_login(estudante)
    response = client.post(
        reverse("challenges:detail", args=[desafio_aberto.pk]),
        {"repo_url": "https://github.com/aluno/api", "description": "Solução"},
        follow=True,
    )
    assert "Este desafio não está aberto para submissões." in response.content.decode()
    assert not Submission.objects.exists()


@pytest.mark.django_db
def test_reabrir_desafioEncerrado_deveRecusar(client, empresa, desafio_aberto):
    Challenge.objects.filter(pk=desafio_aberto.pk).update(status=Challenge.Status.CLOSED)
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:publish", args=[desafio_aberto.pk]), follow=True)

    desafio_aberto.refresh_from_db()
    assert desafio_aberto.status == Challenge.Status.CLOSED
    assert "não pode passar para Aberto" in response.content.decode()


@pytest.mark.django_db
def test_encerrar_rascunho_deveRecusarPorPularEtapa(client, empresa, rascunho):
    client.force_login(empresa.user)

    client.post(reverse("challenges:close", args=[rascunho.pk]))

    rascunho.refresh_from_db()
    assert rascunho.status == Challenge.Status.DRAFT


@pytest.mark.django_db
@pytest.mark.parametrize("rota", ["challenges:publish", "challenges:close"])
def test_mudarSituacao_porGet_naoDeveSerAceito(client, empresa, rascunho, rota):
    client.force_login(empresa.user)

    response = client.get(reverse(rota, args=[rascunho.pk]))

    assert response.status_code == 405
    rascunho.refresh_from_db()
    assert rascunho.status == Challenge.Status.DRAFT


@pytest.mark.django_db
def test_mudarSituacao_deDesafioDeOutraEmpresa_deveRetornar404(client, rascunho):
    from accounts.models import CompanyProfile, User
    outra = User.objects.create_user(username="outra", password="senha-teste-123", role=User.Role.COMPANY)
    CompanyProfile.objects.create(user=outra, company_name="Outra", approved=True)
    client.force_login(outra)

    response = client.post(reverse("challenges:publish", args=[rascunho.pk]))

    assert response.status_code == 404
    rascunho.refresh_from_db()
    assert rascunho.status == Challenge.Status.DRAFT


# ---------- RF06: edição congelada depois da primeira entrega (RN22) ----------

@pytest.mark.django_db
def test_editar_abertoSemSubmissao_devePermitir(client, empresa, desafio_aberto):
    client.force_login(empresa.user)

    client.post(reverse("challenges:edit", args=[desafio_aberto.pk]), _dados(title="API de pedidos v2"))

    desafio_aberto.refresh_from_db()
    assert desafio_aberto.title == "API de pedidos v2"
    assert desafio_aberto.status == Challenge.Status.OPEN  # a edição não mexe na situação


@pytest.mark.django_db
def test_editar_abertoComSubmissao_deveBloquear(client, empresa, estudante, desafio_aberto):
    _entregar(desafio_aberto, estudante)
    client.force_login(empresa.user)

    response = client.post(
        reverse("challenges:edit", args=[desafio_aberto.pk]), _dados(description="Regra nova"), follow=True,
    )

    desafio_aberto.refresh_from_db()
    assert desafio_aberto.description == "Construa uma API REST de pedidos."
    assert "não pode mais ser editado" in response.content.decode()


@pytest.mark.django_db
def test_editar_encerrado_deveBloquear(client, empresa, desafio_aberto):
    Challenge.objects.filter(pk=desafio_aberto.pk).update(status=Challenge.Status.CLOSED)
    client.force_login(empresa.user)

    response = client.get(reverse("challenges:edit", args=[desafio_aberto.pk]))

    assert response.status_code == 302


@pytest.mark.django_db
def test_editar_semAlterarOPrazo_naoDeveReclamarDePrazoJaVencido(client, empresa, rascunho):
    vencido = timezone.now().replace(second=0, microsecond=0) - timedelta(days=2)
    Challenge.objects.filter(pk=rascunho.pk).update(deadline=vencido)
    client.force_login(empresa.user)

    response = client.post(reverse("challenges:edit", args=[rascunho.pk]), {
        "title": "Lista de tarefas v2", "description": "Rascunho.",
        "difficulty": Challenge.Difficulty.BEGINNER,
        "deadline": timezone.localtime(vencido).strftime("%Y-%m-%dT%H:%M"),
    })

    assert response.status_code == 302
    rascunho.refresh_from_db()
    assert rascunho.title == "Lista de tarefas v2"


@pytest.mark.django_db
def test_meusDesafios_mostraAcoesConformeASituacao(client, empresa, estudante, desafio_aberto, rascunho):
    _entregar(desafio_aberto, estudante)
    client.force_login(empresa.user)

    pagina = client.get(reverse("challenges:mine")).content.decode()

    assert reverse("challenges:publish", args=[rascunho.pk]) in pagina
    assert reverse("challenges:edit", args=[rascunho.pk]) in pagina
    assert reverse("challenges:close", args=[desafio_aberto.pk]) in pagina
    assert reverse("challenges:edit", args=[desafio_aberto.pk]) not in pagina  # já recebeu submissão
