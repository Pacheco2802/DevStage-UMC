from django.contrib.auth import get_user_model
from django.db.models import Avg, Count

from challenges.models import Submission

User = get_user_model()


def ranking_estudantes():
    """Estudantes com ao menos uma avaliação, do maior para o menor.
    Desempate: quem tem mais avaliações fica na frente (nota mais consistente)."""
    return (
        User.objects.filter(
            role=User.Role.STUDENT,
            is_active=True,
            is_superuser=False,
            submissions__evaluation__isnull=False,
        )
        .annotate(
            media=Avg("submissions__evaluation__score"),
            avaliacoes=Count("submissions__evaluation"),
        )
        .order_by("-media", "-avaliacoes", "username")
    )


def portfolio_do_estudante(estudante):
    avaliadas = (
        Submission.objects.filter(student=estudante, evaluation__isnull=False)
        .select_related("challenge__company", "evaluation")
        .order_by("-evaluation__score", "-submitted_at")
    )
    resumo = avaliadas.aggregate(media=Avg("evaluation__score"))

    posicao = None
    for indice, aluno in enumerate(ranking_estudantes(), start=1):
        if aluno.pk == estudante.pk:
            posicao = indice
            break

    return {
        "estudante": estudante,
        "avaliadas": avaliadas,
        "media": resumo["media"],
        "total_submissoes": estudante.submissions.count(),
        "posicao": posicao,
    }
