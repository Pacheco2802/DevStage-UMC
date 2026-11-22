"""
Verificação do RNF11: com uma base de 10.000 submissões avaliadas, a lista de desafios,
o ranking e o portfólio respondem em até 2 segundos e com um número fixo de consultas
ao banco, que não cresce com a quantidade de registros.
"""
import time
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import CompanyProfile, User
from challenges.models import Challenge, Evaluation, Submission

ESTUDANTES = 1000
DESAFIOS = 10  # 1.000 estudantes x 10 desafios = 10.000 submissões
LIMITE_SEGUNDOS = 2


@pytest.fixture
def base_grande(db):
    """Monta a base com bulk_create: poucas consultas para inserir milhares de linhas."""
    agora = timezone.now()
    empresa_user = User.objects.create(username="empresa-grande", role=User.Role.COMPANY)
    empresa = CompanyProfile.objects.create(user=empresa_user, company_name="Empresa Grande", approved=True)

    desafios = Challenge.objects.bulk_create([
        Challenge(
            company=empresa, title=f"Desafio {numero}", description="Descrição " * 40,
            deadline=agora + timedelta(days=7), status=Challenge.Status.OPEN,
            difficulty=list(Challenge.Difficulty)[numero % 3],
        )
        for numero in range(DESAFIOS)
    ])
    estudantes = User.objects.bulk_create([
        User(username=f"aluno{numero:04d}", first_name="Aluno", last_name=str(numero), role=User.Role.STUDENT)
        for numero in range(ESTUDANTES)
    ])
    submissoes = Submission.objects.bulk_create([
        Submission(
            challenge=desafio, student=estudante,
            repo_url=f"https://github.com/{estudante.username}/desafio-{desafio.pk}", description="Solução",
        )
        for estudante in estudantes for desafio in desafios
    ])
    Evaluation.objects.bulk_create([
        Evaluation(
            submission=submissao, evaluated_by=empresa_user, score=(indice * 7) % 101,
            strengths="Pontos fortes da entrega.", improvements="Pontos a melhorar da entrega.",
            weight=submissao.challenge.weight, points=((indice * 7) % 101) * submissao.challenge.weight,
        )
        for indice, submissao in enumerate(submissoes)
    ])
    return {"estudantes": estudantes, "desafios": desafios}


def _medir(client, url):
    inicio = time.perf_counter()
    response = client.get(url)
    return response, time.perf_counter() - inicio


@pytest.mark.django_db
def test_base_tem10000SubmissoesAvaliadas(base_grande):
    assert Submission.objects.count() == 10000
    assert Evaluation.objects.count() == 10000


@pytest.mark.django_db
def test_listaDeDesafios_respondeEmAte2sComConsultasFixas(client, base_grande, django_assert_max_num_queries):
    client.force_login(base_grande["estudantes"][0])

    # sessão, usuário, aceite dos termos (2), contagem para a paginação e a página da lista,
    # com a empresa junto (select_related)
    with django_assert_max_num_queries(7):
        response, duracao = _medir(client, reverse("challenges:list"))

    assert response.status_code == 200
    assert len(response.context["challenges"]) == DESAFIOS
    assert duracao < LIMITE_SEGUNDOS


@pytest.mark.django_db
def test_ranking_respondeEmAte2sComUmaConsultaDeAgregacao(client, base_grande, django_assert_max_num_queries):
    # Visitante: a página é pública e o ranking sai de uma única consulta com SUM, AVG e COUNT
    with django_assert_max_num_queries(1):
        response, duracao = _medir(client, reverse("portfolio:ranking"))

    assert response.status_code == 200
    assert response.context["total"] == ESTUDANTES
    assert len(response.context["ranking"]) == 50  # só uma página vai para a tela
    assert duracao < LIMITE_SEGUNDOS


@pytest.mark.django_db
def test_portfolio_respondeEmAte2sComConsultasFixas(client, base_grande, django_assert_max_num_queries):
    estudante = base_grande["estudantes"][0]

    # estudante, perfil (consulta + criação com auditoria), totais, posição no ranking,
    # contagem de submissões e os projetos com desafio, empresa, avaliação e raio-X juntos
    with django_assert_max_num_queries(12):
        response, duracao = _medir(client, reverse("portfolio:detail", args=[estudante.username]))

    assert response.status_code == 200
    assert len(response.context["avaliadas"]) == DESAFIOS
    assert duracao < LIMITE_SEGUNDOS
