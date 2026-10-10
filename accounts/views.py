from django.shortcuts import render, redirect
from django.contrib.auth import login                                                                                                                                                 
from .forms import StudentSignupForm, CompanySignupForm

# Create your views here.

def signup_student(request):
    if request.method == "POST":
        form = StudentSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # loga já cadastrado
            return redirect("challenges:list")
    else:
        form = StudentSignupForm()
    return render(request, "accounts/signup_student.html", {"form": form})

def signup_company(request):
    if request.method == "POST":
        form = CompanySignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # loga já cadastrado
            return redirect("challenges:list")
    else:
        form = CompanySignupForm()
    return render(request, "accounts/signup_company.html", {"form": form})