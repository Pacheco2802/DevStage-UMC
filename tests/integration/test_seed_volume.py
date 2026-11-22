"""
Testes do comando seed_volume, que gera a massa de dados usada nos testes de carga, e da
paginação das listagens, que é o que mantém as telas utilizáveis com milhares de registros.
"""
import pytest
from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from accounts.models import CompanyProfile, StudentProfile, User
from audit.models import AuditLog
from challenges.models import Challenge, Evaluation, RepoSnapshot, Submission
from core.management.commands.seed_volume import DOMINIO_VOLUME
from portfolio.services import linhas_do_ranking


def contas_de_volume():
    return User.objects.filter(email__endswith="@" + DOMINIO_VOLUME)


@pytest.fixture
def volume(db):
    call_command("seed_volume", "--estudantes", "120", "--desafios", "30", "--submissoes", "600")


# ---------- O comando ----------

@pytest.mark.django_db
def test_seedVolume_deveCriarAsQuantidadesPedidas(volume):
    assert contas_de_volume().filter(role=User.Role.STUDENT).count() == 120
    assert Challenge.objects.count() == 30
    assert Submission.objects.count() == 600
    assert RepoSnapshot.objects.count() == 600
    assert StudentProfile.objects.count() == 120
    assert CompanyProfile.objects.filter(approved=True).count() == 20


@pytest.mark.django_db
def test_seedVolume_respeitaAsRegrasDoSistema(volume):
    # uma entrega por estudante em cada desafio
    pares = set(Submission.objects.values_list("student_id", "challenge_id"))
    assert len(pares) == 600
    for submissao in Submission.objects.select_related("challenge"):
        assert submissao.challenge.created_at <= submissao.submitted_at <= submissao.challenge.deadline
    # avaliação só depois do prazo ou do encerramento, com pontos = nota x peso
    assert Evaluation.objects.exists()
    for avaliacao in Evaluation.objects.select_related("submission__challenge"):
        desafio = avaliacao.submission.challenge
        assert desafio.accepts_evaluation
        assert avaliacao.points == avaliacao.score * desafio.weight
    # as três dificuldades e desafios abertos e encerrados
    assert Challenge.objects.values("difficulty").distinct().count() == 3
    assert set(Challenge.objects.values_list("status", flat=True)) == {"OPEN", "CLOSED"}


@pytest.mark.django_db
def test_seedVolume_contasNaoTemSenhaUtilizavel(volume):
    conta = contas_de_volume().filter(role=User.Role.STUDENT).first()

    assert conta.has_usable_password() is False
    assert authenticate(username=conta.username, password="") is None
    assert authenticate(username=conta.username, password="qualquer-senha") is None


@pytest.mark.django_db
def test_seedVolume_naoGravaRegistrosDeAuditoria(volume):
    assert AuditLog.objects.count() == 0


@pytest.mark.django_db
def test_seedVolume_executadoDuasVezes_naoDuplica(volume):
    call_command("seed_volume", "--estudantes", "120", "--desafios", "30", "--submissoes", "600")

    assert Submission.objects.count() == 600


@pytest.mark.django_db
def test_seedVolume_comSubmissoesDemais_deveRecusarSemCriarNada():
    with pytest.raises(CommandError):
        call_command("seed_volume", "--estudantes", "10", "--desafios", "5", "--submissoes", "500")

    assert not contas_de_volume().exists()


@pytest.mark.django_db
def test_seedVolume_limpar_removeSoAMassaDeVolume(volume, estudante, desafio_aberto):
    Submission.objects.create(
        challenge=desafio_aberto, student=estudante, repo_url="https://github.com/aluno/api", description="Real",
    )
    registros_antes = AuditLog.objects.count()

    call_command("seed_volume", "--limpar")

    assert not contas_de_volume().exists()
    assert Submission.objects.count() == 1  # a entrega que não é da massa de volume continua
    assert Challenge.objects.filter(pk=desafio_aberto.pk).exists()
    # a limpeza não enche a auditoria com milhares de exclusões
    assert AuditLog.objects.count() == registros_antes


# ---------- Ranking paginado ----------

@pytest.mark.django_db
def test_ranking_mostra50PorPaginaEMantemAPosicaoGeral(client, volume):
    total = len(linhas_do_ranking())
    assert total > 50

    primeira = client.get(reverse("portfolio:ranking"))
    segunda = client.get(reverse("portfolio:ranking"), {"pagina": 2})

    assert primeira.context["total"] == total
    assert len(primeira.context["ranking"]) == 50
    assert [linha.posicao for linha in primeira.context["ranking"]][:3] == [1, 2, 3]
    assert segunda.context["ranking"][0].posicao == 51
    assert segunda.context["podio"] == []  # o pódio só aparece na primeira página


@pytest.mark.django_db
def test_ranking_buscaFiltraMasNaoMudaAPosicao(client, volume):
    alvo = linhas_do_ranking()[69]  # o 70º colocado, que fica na segunda página

    response = client.get(reverse("portfolio:ranking"), {"q": alvo.username})

    assert [linha.posicao for linha in response.context["ranking"]] == [70]
    assert response.context["podio"] == []
    assert alvo.nome in response.content.decode()


@pytest.mark.django_db
def test_ranking_buscaSemResultado_deveAvisar(client, volume):
    response = client.get(reverse("portfolio:ranking"), {"q": "nome-que-nao-existe"})

    assert response.status_code == 200
    assert "Nenhum estudante encontrado com esse nome." in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("pagina", ["abc", "0", "-3", "9999"])
def test_ranking_paginaInvalida_naoDaErro(client, volume, pagina):
    response = client.get(reverse("portfolio:ranking"), {"pagina": pagina})

    assert response.status_code == 200
    assert len(response.context["ranking"]) > 0


@pytest.mark.django_db
def test_ranking_minhaPosicao_apontaParaAPaginaCerta(client, volume):
    linha = linhas_do_ranking()[69]
    client.force_login(User.objects.get(pk=linha.pk))

    response = client.get(reverse("portfolio:ranking"))

    assert response.context["minha_linha"].posicao == 70
    assert response.context["minha_pagina"] == 2
    assert 'href="?pagina=2#eu"' in response.content.decode()


# ---------- Lista de projetos e submissões recebidas ----------

@pytest.mark.django_db
def test_listaDeProjetos_mostra12PorPagina(client, estudante, volume):
    client.force_login(estudante)
    abertos = Challenge.objects.filter(status=Challenge.Status.OPEN).count()
    assert abertos == 12  # 4 em cada 10 desafios da massa de volume estão abertos

    for numero in range(3):
        Challenge.objects.create(
            company=CompanyProfile.objects.first(), title=f"Extra {numero}", description="x",
            deadline=Challenge.objects.filter(status="OPEN").first().deadline, status=Challenge.Status.OPEN,
        )
    primeira = client.get(reverse("challenges:list"))
    segunda = client.get(reverse("challenges:list"), {"pagina": 2})

    assert primeira.context["challenges"].paginator.count == 15
    assert len(primeira.context["challenges"]) == 12
    assert len(segunda.context["challenges"]) == 3
    assert "página 1 de 2" in primeira.content.decode()


@pytest.mark.django_db
def test_listaDeProjetos_buscaPorTituloEmpresaEDificuldade(client, estudante, empresa, desafio_aberto, volume):
    client.force_login(estudante)

    por_titulo = client.get(reverse("challenges:list"), {"q": "api de pedidos"})
    por_empresa = client.get(reverse("challenges:list"), {"q": "acme"})
    por_dificuldade = client.get(reverse("challenges:list"), {"dificuldade": "ADVANCED"})
    sem_resultado = client.get(reverse("challenges:list"), {"q": "nada-parecido"})

    assert [desafio.pk for desafio in por_titulo.context["challenges"]] == [desafio_aberto.pk]
    assert [desafio.pk for desafio in por_empresa.context["challenges"]] == [desafio_aberto.pk]
    assert {desafio.difficulty for desafio in por_dificuldade.context["challenges"]} == {"ADVANCED"}
    assert "Nenhum projeto encontrado" in sem_resultado.content.decode()


@pytest.mark.django_db
def test_listaDeProjetos_paginacaoMantemABusca(client, estudante, volume):
    client.force_login(estudante)
    for numero in range(14):
        Challenge.objects.create(
            company=CompanyProfile.objects.first(), title=f"Projeto especial {numero}", description="x",
            deadline=Challenge.objects.filter(status="OPEN").first().deadline, status=Challenge.Status.OPEN,
        )

    response = client.get(reverse("challenges:list"), {"q": "especial"})

    assert response.context["challenges"].paginator.count == 14
    assert "?q=especial&amp;pagina=2" in response.content.decode()


@pytest.mark.django_db
def test_submissoesRecebidas_mostra20PorPagina(client, volume):
    desafio = max(Challenge.objects.all(), key=lambda d: d.submissions.count())
    total = desafio.submissions.count()
    assert total > 20
    dona = desafio.company.user
    client.force_login(dona)

    response = client.get(reverse("challenges:submissions", args=[desafio.pk]))

    assert len(response.context["submissions"]) == 20
    assert response.context["submissions"].paginator.count == total
    assert f"{total} submissões" in response.content.decode()
