from django.contrib import admin

from .models import AuditLog

# Register your models here.

# Como cada campo acompanhado aparece para o administrador
CHANGE_LABELS = {
    "score": "Nota",
    "points": "Pontos",
    "status": "Situação",
    "difficulty": "Dificuldade",
    "deadline": "Prazo",
}


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "user", "action", "target_model", "target_id", "alteracao", "path", "ip"]
    list_filter = ["action", "target_model", "timestamp"]
    search_fields = ["user__username", "path", "target_id"]
    fields = ["timestamp", "user", "action", "target_model", "target_id", "alteracao", "path", "ip"]
    readonly_fields = fields

    @admin.display(description="Alteração")
    def alteracao(self, obj):
        """Valor anterior e novo de cada campo acompanhado, como em 'Nota: 70 → 85'."""
        return "; ".join(
            f"{CHANGE_LABELS.get(field, field)}: {old} → {new}" for field, (old, new) in obj.changes.items()
        ) or "-"

    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
