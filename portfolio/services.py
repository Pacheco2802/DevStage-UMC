from collections import namedtuple

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Sum

from accounts.models import StudentProfile
from challenges.models import Submission

User = get_user_model()


def ranking_estudantes():
    """Ranking por pontos (RN48), calculado por agregação das avaliações gravadas (RN50).

    Desempate: maior média de notas e, se persistir, ordem alfabética do nome de usuário.
    Ficam de fora quem não tem avaliação, contas desativadas e portfólios privados (RN49)."""
    return (
        User.objects.filter(
            role=User.Role.STUDENT,
            is_active=True,
            is_superuser=False,
            submissions__evaluation__isnull=False,
        )
        # Conta sem perfil (criada fora do cadastro) vale como pública, que é o padrão do perfil
        .exclude(student_profile__portfolio_public=False)
        .annotate(
            pontos=Sum("submissions__evaluation__points"),
            media=Avg("submissions__evaluation__score"),
            avaliacoes=Count("submissions__evaluation"),
        )
        .order_by("-pontos", "-media", "username")
    )


# Uma linha do ranking pronta para a tela: só o que a página mostra, já com a posição
Linha = namedtuple("Linha", ["posicao", "pk", "username", "nome", "pontos", "media", "avaliacoes"])


def linhas_do_ranking():
    """Ranking completo em uma única consulta, como linhas leves em vez de objetos User.

    A página mostra só um trecho por vez, mas a posição de cada estudante depende de todos os
    que estão à frente, então a ordem inteira é calculada aqui e a paginação corta depois."""
    dados = ranking_estudantes().values_list(
        "pk", "username", "first_name", "last_name", "pontos", "media", "avaliacoes"
    )
    return [
        Linha(posicao, pk, username, f"{nome} {sobrenome}".strip() or username, pontos, media, avaliacoes)
        for posicao, (pk, username, nome, sobrenome, pontos, media, avaliacoes) in enumerate(dados, start=1)
    ]


def posicao_no_ranking(estudante):
    """Posição do estudante no ranking, ou None se ele não aparece nele."""
    ids = list(ranking_estudantes().values_list("pk", flat=True))
    return ids.index(estudante.pk) + 1 if estudante.pk in ids else None


def portfolio_do_estudante(estudante):
    avaliadas = (
        Submission.objects.filter(student=estudante, evaluation__isnull=False)
        .select_related("challenge__company", "evaluation", "snapshot")
        .order_by("-evaluation__points", "-submitted_at")
    )
    resumo = avaliadas.aggregate(media=Avg("evaluation__score"), pontos=Sum("evaluation__points"))

    return {
        "estudante": estudante,
        "perfil": StudentProfile.for_user(estudante),
        "avaliadas": avaliadas,
        "media": resumo["media"],
        "pontos": resumo["pontos"] or 0,
        "total_submissoes": estudante.submissions.count(),
        "posicao": posicao_no_ranking(estudante),
    }
