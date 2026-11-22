from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User
from .models import CompanyProfile
from .models import ConsentLog, LoginAttempt, TermsVersion

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


@admin.register(TermsVersion)
class TermsVersionAdmin(admin.ModelAdmin):
    # Somente leitura: uma versão é publicada por migração, junto com o texto, e não muda depois
    list_display = ["version", "published_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    # Somente consulta: o administrador vê as tentativas que falharam; excluir uma libera o login
    list_display = ["username", "ip", "failed_at"]
    list_filter = ["failed_at"]
    search_fields = ["username", "ip"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
