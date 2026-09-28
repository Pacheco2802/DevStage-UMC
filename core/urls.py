from django.urls import path                                                                                      
from django.views.generic import TemplateView

app_name = "core"

urlpatterns = [
    path("termos/", TemplateView.as_view(template_name="core/termos.html"), name="terms"),
    path("privacidade/", TemplateView.as_view(template_name="core/privacidade.html"), name="privacy"),
]