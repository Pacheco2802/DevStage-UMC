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
