from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import StudentProfile
from core.decorators import student_required

from .forms import StudentProfileForm
from .services import portfolio_do_estudante, ranking_estudantes

User = get_user_model()


def ranking(request):
    # Página pública (RF14): visitantes também veem o ranking, só com portfólios públicos
    alunos = list(ranking_estudantes())
    return render(request, "portfolio/ranking.html", {
        "ranking": alunos,
        "max_pontos": alunos[0].pontos if alunos else 0,
    })


def student_portfolio(request, username):
    # Conta desativada/anonimizada (LGPD) não tem portfólio exibido
    estudante = get_object_or_404(User, username=username, role=User.Role.STUDENT, is_active=True)
    contexto = portfolio_do_estudante(estudante)
    # RN53: portfólio privado responde como não encontrado; só o próprio estudante continua vendo
    if not contexto["perfil"].portfolio_public and request.user != estudante:
        raise Http404
    return render(request, "portfolio/detail.html", contexto)


@student_required
def edit_profile(request):
    perfil = StudentProfile.for_user(request.user)
    form = StudentProfileForm(request.POST or None, instance=perfil)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil atualizado.")
        return redirect("portfolio:detail", username=request.user.username)
    return render(request, "portfolio/edit_profile.html", {"form": form, "perfil": perfil})
