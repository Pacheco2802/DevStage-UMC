from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User
from .models import CompanyProfile
from .models import ConsentLog

# Register your models here.
@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = DjangoUserAdmin.list_display + ('role',)
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Papel na plataforma", {"fields": ("role",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Papel na plataforma", {"fields": ("role",)}),
    )

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ["company_name", "user", "approved", "created_at"]
    list_filter = ["approved"]
    search_fields = ["company_name", "user__username"]


@admin.register(ConsentLog)
class ConsentLogAdmin(admin.ModelAdmin):
    # Somente leitura: o registro do aceite é prova, não pode ser alterado pelo admin
    list_display = ["user", "terms_version", "accepted_at", "ip", "revoked_at"]
    list_filter = ["terms_version", "revoked_at"]
    search_fields = ["user__username", "ip"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
