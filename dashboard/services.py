from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import CompanyProfile
from challenges.models import Challenge, Evaluation, Submission

User = get_user_model()

DIAS_NA_SERIE = 30
TOP_DESAFIOS = 5


def perfil_do_dashboard(user):
    # createsuperuser cria o usuário com role padrão (STUDENT), por isso is_superuser também conta como admin
    if user.is_superuser or user.role == User.Role.PLATFORM_ADMIN:
        return "ADMIN"
    return user.role


def _escopo(user, perfil):
    """Querysets que cada perfil enxerga: a mesma métrica muda conforme quem está logado."""
    desafios = Challenge.objects.all()
    submissoes = Submission.objects.all()
    if perfil == User.Role.COMPANY:
        desafios = desafios.filter(company__user=user)
        submissoes = submissoes.filter(challenge__company__user=user)
    elif perfil == User.Role.STUDENT:
        submissoes = submissoes.filter(student=user)
        desafios = desafios.filter(submissions__student=user)  # desafios em que o estudante participou
    return desafios, submissoes


def _big_numbers(user, perfil, desafios, submissoes):
    abertos = Challenge.objects.filter(status=Challenge.Status.OPEN, deadline__gte=timezone.now())

    if perfil == "ADMIN":
        return [
            {"rotulo": "Desafios abertos", "valor": abertos.count()},
            {"rotulo": "Submissões", "valor": submissoes.count()},
            {
                "rotulo": "Estudantes",
                "valor": User.objects.filter(role=User.Role.STUDENT, is_active=True, is_superuser=False).count(),
            },
            {"rotulo": "Empresas aguardando aprovação", "valor": CompanyProfile.objects.filter(approved=False).count()},
            {"rotulo": "Avaliações feitas", "valor": Evaluation.objects.count()},
        ]
    if perfil == User.Role.COMPANY:
        return [
            {"rotulo": "Desafios publicados", "valor": desafios.count()},
            {"rotulo": "Desafios abertos", "valor": abertos.filter(company__user=user).count()},
            {"rotulo": "Submissões recebidas", "valor": submissoes.count()},
            {"rotulo": "Estudantes participantes", "valor": submissoes.values("student").distinct().count()},
            {"rotulo": "Aguardando avaliação", "valor": submissoes.filter(evaluation__isnull=True).count()},
        ]
    return [
        {"rotulo": "Submissões enviadas", "valor": submissoes.count()},
        {"rotulo": "Desafios abertos", "valor": abertos.count()},
        {"rotulo": "Abertos sem a sua submissão", "valor": abertos.exclude(submissions__student=user).count()},
        {"rotulo": "Nota média", "valor": _media(submissoes)},
    ]


def _media(submissoes):
    media = submissoes.aggregate(media=Avg("evaluation__score"))["media"]
    return round(media, 1) if media is not None else None  # None = ainda sem avaliação


def _submissoes_por_dia(submissoes):
    hoje = timezone.localdate()
    inicio = hoje - timedelta(days=DIAS_NA_SERIE - 1)
    contagem = dict(
        submissoes.filter(submitted_at__date__gte=inicio)
        .annotate(dia=TruncDate("submitted_at", tzinfo=timezone.get_current_timezone()))
        .values("dia")
        .annotate(total=Count("id"))
        .values_list("dia", "total")
    )
    # Dias sem submissão entram com zero para a linha do tempo não "pular" datas
    dias = [inicio + timedelta(days=i) for i in range(DIAS_NA_SERIE)]
    return [{"label": dia.strftime("%d/%m"), "valor": contagem.get(dia, 0)} for dia in dias]


def _desafios_por_status(desafios):
    contagem = dict(
        desafios.values("status").annotate(total=Count("id", distinct=True)).values_list("status", "total")
    )
    return [{"label": rotulo, "valor": contagem.get(status, 0)} for status, rotulo in Challenge.Status.choices]


def _top_desafios(desafios, perfil):
    if perfil == User.Role.STUDENT:
        return []  # para o estudante, cada desafio tem no máximo 1 submissão dele
    ranking = desafios.annotate(total=Count("submissions")).order_by("-total", "title")[:TOP_DESAFIOS]
    return [{"label": d.title, "valor": d.total} for d in ranking]


def dashboard_data(user):
    perfil = perfil_do_dashboard(user)
    desafios, submissoes = _escopo(user, perfil)
    return {
        "perfil": perfil,
        "big_numbers": _big_numbers(user, perfil, desafios, submissoes),
        "submissoes_por_dia": _submissoes_por_dia(submissoes),
        "desafios_por_status": _desafios_por_status(desafios),
        "top_desafios": _top_desafios(desafios, perfil),
    }
