from django.contrib import admin
from .models import Challenge
from .models import Submission
from .models import Evaluation
from .models import RepoSnapshot

# Register your models here.
@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "difficulty", "status", "deadline", "created_at"]
    list_filter = ["status", "difficulty"]
    search_fields = ["title", "company__company_name"]
    date_hierarchy = "deadline"

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ["challenge", "student", "submitted_at"]
    list_filter = ["submitted_at"]
    search_fields = ["challenge__title", "student__username", "repo_url"]
    autocomplete_fields = ["challenge", "student"]
    readonly_fields = ["submitted_at"]


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    # RN44: a empresa não altera a avaliação. A correção é feita aqui, pelo administrador, e fica
    # registrada na auditoria. Peso e pontos não são digitados: o save recalcula os pontos.
    list_display = ["submission", "score", "points", "evaluated_by", "evaluated_at"]
    list_filter = ["evaluated_at"]
    search_fields = ["submission__challenge__title", "submission__student__username"]
    readonly_fields = ["submission", "evaluated_by", "weight", "points", "evaluated_at", "updated_at"]

    def has_add_permission(self, request):
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
