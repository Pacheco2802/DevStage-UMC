from django.urls import include, path
from . import views

urlpatterns = [
    path("", include("django.contrib.auth.urls")),
    path("signup/estudante/", views.signup_student, name="signup_student"),
    path("signup/empresa/", views.signup_company, name="signup_company"),
]
