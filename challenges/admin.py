from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import Challenge, Evaluation, RepoSnapshot, Submission


class ChallengeAdminForm(forms.ModelForm):
    """As regras do ciclo de vida valem também na área administrativa, e não só nas telas da empresa."""

    def clean_status(self):
        new_status = self.cleaned_data["status"]
        challenge = self.instance  # ainda com a situação gravada: o formulário só a troca depois
        if not challenge.pk or new_status == challenge.status:
            return new_status
        # RN21: Rascunho -> Aberto -> Encerrado, sem voltar e sem pular etapa
        if not challenge.can_transition_to(new_status):
            raise ValidationError(
                f"Um desafio com situação {challenge.get_status_display()} não pode passar para "
                f"{Challenge.Status(new_status).label}."
            )
        # RN19: ninguém conseguiria entregar em um desafio publicado com o prazo já vencido
        if new_status == Challenge.Status.OPEN and challenge.deadline_passed:
            raise ValidationError("O prazo deste desafio já passou. Edite o prazo antes de publicar.")
        return new_status


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    form = ChallengeAdminForm
    list_display = ["title", "company", "difficulty", "status", "deadline", "created_at"]
    list_filter = ["status", "difficulty"]
    search_fields = ["title", "company__company_name"]
    date_hierarchy = "deadline"

    # RN22: o que a empresa não pode mais editar depois da primeira entrega também fica travado aqui
    FROZEN_FIELDS = ["company", "title", "description", "deadline", "difficulty"]

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and not obj.is_editable:
            return self.FROZEN_FIELDS
        return []

    def has_delete_permission(self, request, obj=None):
        # Excluir o desafio apagaria em cascata as entregas e as notas dos estudantes
        if obj is not None and obj.submissions.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    # Somente consulta: a entrega é a evidência do que o estudante enviou no prazo. Como ela não pode
    # ser excluída aqui, o admin também recusa excluir o desafio ou o usuário que a levaria em cascata.
    list_display = ["challenge", "student", "submitted_at"]
    list_filter = ["submitted_at"]
    search_fields = ["challenge__title", "student__username", "repo_url"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    # RN44: a empresa não altera a avaliação. A correção é feita aqui, pelo administrador, e fica
    # registrada na auditoria com a nota anterior e a nova. Peso e pontos não são digitados: o save
    # recalcula os pontos. Corrige-se editando: a avaliação não pode ser excluída.
    list_display = ["submission", "score", "points", "evaluated_by", "evaluated_at"]
    list_filter = ["evaluated_at"]
    search_fields = ["submission__challenge__title", "submission__student__username"]
    readonly_fields = ["submission", "evaluated_by", "weight", "points", "evaluated_at", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RepoSnapshot)
class RepoSnapshotAdmin(admin.ModelAdmin):
    # Somente leitura: o commit registrado na entrega é evidência e não pode ser trocado pelo admin
    list_display = ["submission", "status", "main_language", "commit_sha", "created_at"]
    list_filter = ["status", "main_language"]
    search_fields = ["submission__student__username", "commit_sha"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
