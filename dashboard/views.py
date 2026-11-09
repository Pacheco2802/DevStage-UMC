from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import dashboard_data


@login_required
def dashboard(request):
    # Big Numbers já vêm renderizados no HTML; os gráficos buscam o endpoint JSON abaixo
    return render(request, "dashboard/index.html", {"data": dashboard_data(request.user)})


class DashboardDataAPI(APIView):
    """GET /dashboard/api/dados/ → indicadores e séries dos gráficos, filtrados pelo perfil logado."""

    def get(self, request):
        return Response(dashboard_data(request.user))
