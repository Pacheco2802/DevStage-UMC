from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User
from .models import CompanyProfile

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
