from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import StudentProfile
from core.decorators import student_required
from core.pagination import filtros_da_url, paginar

from .forms import StudentProfileForm
from .services import linhas_do_ranking, portfolio_do_estudante

User = get_user_model()

ESTUDANTES_POR_PAGINA = 50


def ranking(request):
    # Página pública (RF14): visitantes também veem o ranking, só com portfólios públicos
    linhas = linhas_do_ranking()
    termo = request.GET.get("q", "").strip()
    encontradas = linhas
    if termo:
        # A busca filtra o que aparece, mas a posição continua sendo a do ranking geral
        alvo = termo.lower()
        encontradas = [linha for linha in linhas if alvo in linha.nome.lower() or alvo in linha.username.lower()]
    pagina = paginar(request, encontradas, ESTUDANTES_POR_PAGINA)

    minha_linha = None
    if request.user.is_authenticated:
        minha_linha = next((linha for linha in linhas if linha.pk == request.user.pk), None)

    return render(request, "portfolio/ranking.html", {
        "ranking": pagina,
        "total": len(linhas),
        "termo": termo,
        # O pódio destaca os três primeiros do ranking geral, na primeira página e sem busca
        "podio": linhas[:3] if len(linhas) >= 3 and not termo and pagina.number == 1 else [],
        "max_pontos": linhas[0].pontos if linhas else 0,
        "minha_linha": minha_linha,
        "minha_pagina": (minha_linha.posicao - 1) // ESTUDANTES_POR_PAGINA + 1 if minha_linha else None,
        "filtros": filtros_da_url(request),
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
