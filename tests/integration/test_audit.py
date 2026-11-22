"""
Testes de integração da trilha de auditoria (RF17): quem fez cada alteração (RN60),
registros somente leitura (RN57) e preservação após a remoção do usuário (RN58).
"""
from datetime import timedelta

import pytest
from django.contrib.admin.sites import site
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from audit.middleware import current_actor
from audit.models import AuditLog
from challenges.models import Challenge, Evaluation, Submission


def _ultimo(target_model, action):
    return AuditLog.objects.filter(target_model=target_model, action=action).first()


# ---------- RN60: o autor da alteração ----------

@pytest.mark.django_db
def test_criarDesafio_deveRegistrarAEmpresaOCaminhoEOIp(client, empresa):
    client.force_login(empresa.user)

    client.post(reverse("challenges:create"), {
        "title": "Novo desafio", "description": "Descrição", "difficulty": "BEGINNER",
        "deadline": (timezone.localtime() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"), "status": "OPEN",
    }, REMOTE_ADDR="10.0.0.5")

    registro = _ultimo("Challenge", AuditLog.Action.CREATE)
    assert registro.user == empresa.user
    assert registro.path == reverse("challenges:create")
    assert registro.ip == "10.0.0.5"
    assert registro.target_id == str(Challenge.objects.get().pk)


@pytest.mark.django_db
def test_submeter_deveRegistrarOEstudanteComoAutor(client, estudante, desafio_aberto, monkeypatch):
    from integrations.github_client import GitHubValidationResult
    monkeypatch.setattr("challenges.forms.repo_exists", lambda url: GitHubValidationResult(True))
    client.force_login(estudante)

    client.post(reverse("challenges:detail", args=[desafio_aberto.pk]), {
        "repo_url": "https://github.com/aluno/api", "description": "Minha solução",
    })

    registro = _ultimo("Submission", AuditLog.Action.CREATE)
    assert registro.user == estudante
    assert registro.target_id == str(Submission.objects.get().pk)


@pytest.mark.django_db
def test_avaliar_deveRegistrarAEmpresaComoAutoraDaAvaliacao(client, empresa, estudante, desafio_aberto):
    submissao = Submission.objects.create(
        challenge=desafio_aberto, student=estudante, repo_url="https://github.com/aluno/api", description="x",
    )
    Challenge.objects.filter(pk=desafio_aberto.pk).update(status=Challenge.Status.CLOSED)
    client.force_login(empresa.user)

    client.post(reverse("challenges:evaluate", args=[submissao.pk]), {
        "score": 80, "strengths": "Boa organização do código.", "improvements": "Faltaram testes dos erros.",
    })

    registro = _ultimo("Evaluation", AuditLog.Action.CREATE)
    assert registro.user == empresa.user
    assert registro.target_id == str(Evaluation.objects.get().pk)


@pytest.mark.django_db
def test_cadastroDeVisitante_naoTemAutorMasGuardaCaminhoEIp(client):
    client.post(reverse("signup_student"), {
        "username": "novoaluno", "email": "novo@aluno.com", "first_name": "Novo",
        "password1": "Senha-Forte-2026!", "password2": "Senha-Forte-2026!", "accept_lgpd": "on",
    }, REMOTE_ADDR="10.0.0.7")

    registro = AuditLog.objects.filter(target_model="User", action=AuditLog.Action.CREATE).last()
    assert registro.user is None
    assert registro.path == reverse("signup_student")
    assert registro.ip == "10.0.0.7"


@pytest.mark.django_db
def test_alteracaoForaDeRequisicao_ficaSemAutor(empresa):
    # Criado direto pelo ORM, como em um comando de terminal: não há requisição em andamento
    Challenge.objects.create(
        company=empresa, title="Via terminal", description="x", deadline=timezone.now() + timedelta(days=1),
    )

    registro = _ultimo("Challenge", AuditLog.Action.CREATE)
    assert registro.user is None
    assert registro.path == ""
    assert current_actor() == {"user": None, "path": "", "ip": None}


@pytest.mark.django_db
def test_autorNaoVazaDeUmaRequisicaoParaAProxima(client, empresa, desafio_aberto):
    client.force_login(empresa.user)
    client.get(reverse("challenges:mine"))

    # Depois que a requisição termina, o contexto volta ao estado inicial
    assert current_actor()["user"] is None


# ---------- RN57 e RN58 ----------

@pytest.mark.django_db
def test_admin_naoPermiteIncluirAlterarNemExcluirRegistros(rf, admin_user):
    request = rf.get("/admin/audit/auditlog/")
    request.user = admin_user
    audit_admin = site._registry[AuditLog]

    assert audit_admin.has_add_permission(request) is False
    assert audit_admin.has_change_permission(request) is False
    assert audit_admin.has_delete_permission(request) is False


@pytest.mark.django_db
def test_admin_listagemDeLogs_abreParaOAdministrador(admin_client, settings):
    # Em produção os estáticos passam pelo collectstatic; no teste, a página usa os arquivos direto
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    AuditLog.objects.create(action=AuditLog.Action.ACCESS, target_model="DataExport")

    response = admin_client.get("/admin/audit/auditlog/")

    assert response.status_code == 200
    assert "DataExport" in response.content.decode()


@pytest.mark.django_db
def test_removerUsuario_devePreservarOsRegistrosSemOVinculo(estudante):
    registro = AuditLog.objects.create(user=estudante, action=AuditLog.Action.LOGIN, path="/accounts/login/")

    User.objects.filter(pk=estudante.pk).delete()

    registro.refresh_from_db()
    assert registro.user is None
    assert "anônimo" in str(registro)


@pytest.mark.django_db
def test_seedDemo_rodadoPeloTerminal_naoQuebraAAuditoria(monkeypatch, settings):
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "demo-Senha-2026")

    call_command("seed_demo")

    assert AuditLog.objects.filter(target_model="Evaluation", user__isnull=True).exists()
