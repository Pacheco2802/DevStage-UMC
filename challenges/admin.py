from django.contrib import admin
from .models import Challenge
from .models import Submission

# Register your models here.
@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "status", "deadline", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "company__company_name"]
    date_hierarchy = "deadline"

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ["challenge", "student", "submitted_at"]
    list_filter = ["submitted_at"]
    search_fields = ["challenge__title", "student__username", "repo_url"]
    autocomplete_fields = ["challenge", "student"]
    readonly_fields = ["submitted_at"]