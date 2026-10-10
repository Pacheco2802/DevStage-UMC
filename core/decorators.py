from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

def student_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != request.user.Role.STUDENT:
            messages.error(request, "Apenas estudantes podem acessar esta página.")
            return redirect("challenges:list")
        return view_func(request, *args, **kwargs)
    return wrapper

def company_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != request.user.Role.COMPANY:
            messages.error(request, "Apenas empresas podem acessar esta página.")
            return redirect("challenges:list")
        return view_func(request, *args, **kwargs)
    return wrapper

def approved_company_required(view_func):
    @wraps(view_func)
    @company_required
    def wrapper(request, *args, **kwargs):
        if not request.user.company_profile.approved:
            messages.error(request, "Sua empresa ainda não foi aprovada por um administrador.")
            return redirect("challenges:list")
        return view_func(request, *args, **kwargs)
    return wrapper