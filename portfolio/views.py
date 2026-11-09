from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .services import portfolio_do_estudante, ranking_estudantes

User = get_user_model()


@login_required
def ranking(request):
    return render(request, "portfolio/ranking.html", {"ranking": ranking_estudantes()})


@login_required
def student_portfolio(request, username):
    # Conta desativada/anonimizada (LGPD) não tem portfólio exibido
    estudante = get_object_or_404(User, username=username, role=User.Role.STUDENT, is_active=True)
    return render(request, "portfolio/detail.html", portfolio_do_estudante(estudante))
