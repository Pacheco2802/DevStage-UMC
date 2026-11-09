from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from core.utils import get_client_ip
from .forms import StudentSignupForm, CompanySignupForm, MyDataForm, CompanyDataForm
from .services import anonymize_user, export_user_data, record_consent, revoke_consent

# Create your views here.

def signup_student(request):
    if request.method == "POST":
        form = StudentSignupForm(request.POST)
        if form.is_valid():
            # Usuário e aceite juntos: se um falhar, nenhum dos dois fica salvo
            with transaction.atomic():
                user = form.save()
                record_consent(user, request)
            login(request, user) # loga já cadastrado
            return redirect("challenges:list")
    else:
        form = StudentSignupForm()
    return render(request, "accounts/signup_student.html", {"form": form})

def signup_company(request):
    if request.method == "POST":
        form = CompanySignupForm(request.POST)
        if form.is_valid():
            # Usuário e aceite juntos: se um falhar, nenhum dos dois fica salvo
            with transaction.atomic():
                user = form.save()
                record_consent(user, request)
            login(request, user) # loga já cadastrado
            return redirect("challenges:list")
    else:
        form = CompanySignupForm()
    return render(request, "accounts/signup_company.html", {"form": form})

@login_required
def my_data(request):
    user = request.user
    company = getattr(user, "company_profile", None)

    if request.method == "POST":
        form = MyDataForm(request.POST, instance=user)
        company_form = CompanyDataForm(request.POST, instance=company) if company else None
        if form.is_valid() and (company_form is None or company_form.is_valid()):
            form.save()
            if company_form:
                company_form.save()
            messages.success(request, "Dados atualizados com sucesso.")
            return redirect("my_data")
    else:
        form = MyDataForm(instance=user)
        company_form = CompanyDataForm(instance=company) if company else None

    return render(request, "accounts/my_data.html", {
        "form": form,
        "company_form": company_form,
        "consents": user.consents.all(),
        "submissions": user.submissions.select_related("challenge"),
        "audit_logs": AuditLog.objects.filter(user=user)[:10],
    })


@login_required
def my_data_export(request):
    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.ACCESS,
        target_model="DataExport",
        path=request.path,
        ip=get_client_ip(request),
    )
    response = JsonResponse(export_user_data(request.user), json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = f'attachment; filename="devstage-meus-dados-{request.user.pk}.json"'
    return response


@login_required
@require_POST
def my_data_delete(request):
    # Exige digitar o username para confirmar — evita exclusão por clique acidental
    if request.POST.get("confirm_username") != request.user.username:
        messages.error(request, "Confirmação inválida: digite exatamente o seu nome de usuário.")
        return redirect("my_data")

    user = request.user
    logout(request)
    anonymize_user(user)
    messages.success(request, "Sua conta foi eliminada e seus dados pessoais foram anonimizados.")
    return redirect("login")


@login_required
@require_POST
def revoke_consent_view(request):
    user = request.user
    logout(request)
    revoke_consent(user)
    messages.success(request, "Consentimento revogado. Sua conta foi desativada.")
    return redirect("login")
