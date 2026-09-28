from django.contrib import admin
from .models import AuditLog

# Register your models here.

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "target_model", "target_id", "path", "ip")
    list_filter = ("action", "target_model", "timestamp")
    search_fields = ("user__username", "path", "target_id")
    readonly_fields = ("user", "action", "target_model", "target_id", "path", "ip", "timestamp")

    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False