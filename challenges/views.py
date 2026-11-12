from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import approved_company_required, company_required, student_required

from .forms import ChallengeForm, EvaluationForm, SubmissionForm
from .models import Challenge, Evaluation, Submission


@login_required
def challenge_list(request):
    challenges = Challenge.objects.filter(status=Challenge.Status.OPEN)
    return render(request, "challenges/list.html", {"challenges": challenges})


@login_required
def challenge_detail(request, pk):
    challenge = get_object_or_404(Challenge, pk=pk)
    # Rascunho ainda não foi publicado: só a empresa dona enxerga
    if challenge.status == Challenge.Status.DRAFT and challenge.company.user_id != request.user.pk:
        raise Http404

    user_submission = Submission.objects.filter(
        challenge=challenge, student=request.user
    ).first()

    can_submit, block_reason = _check_can_submit(challenge, request.user, user_submission)

    if request.method == "POST":
        if not can_submit:
            messages.error(request, block_reason)
            return redirect("challenges:detail", pk=pk)

        form = SubmissionForm(request.POST)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.challenge = challenge
            submission.student = request.user
            submission.save()
            messages.success(request, "Entrega registrada com sucesso!")
            return redirect("challenges:detail", pk=pk)
    else:
        form = SubmissionForm()

    return render(
        request,
        "challenges/detail.html",
        {
            "challenge": challenge,
            "form": form,
            "user_submission": user_submission,
            "can_submit": can_submit,
            "block_reason": block_reason,
        },
    )


def _check_can_submit(challenge, user, existing_submission):
    if user.role != user.Role.STUDENT:
        return False, "Apenas usuários com perfil de estudante podem submeter."
    if challenge.status != Challenge.Status.OPEN:
        return False, "Este desafio não está aberto para submissões."
    if challenge.deadline < timezone.now():
        return False, "O prazo deste desafio já venceu."
    if existing_submission is not None:
        return False, "Você já enviou uma submissão para este desafio."
    return True, ""

@approved_company_required
def challenge_create(request):
    if request.method == "POST":
        form = ChallengeForm(request.POST)
        if form.is_valid():
            challenge = form.save(commit=False)
            challenge.company = request.user.company_profile
            challenge.save()
            messages.success(request, "Desafio criado com sucesso!")
            return redirect("challenges:detail", pk=challenge.pk)
    else:
        form = ChallengeForm()

    return render(request, "challenges/create.html", {"form": form})


# ---------- Painel da empresa ----------

def _desafio_da_empresa(request, pk):
    # Filtra pelo dono: desafio de outra empresa devolve 404, sem revelar que ele existe
    return get_object_or_404(Challenge, pk=pk, company__user=request.user)


@company_required
def my_challenges(request):
    challenges = (
        Challenge.objects.filter(company__user=request.user)
        .annotate(total_submissions=Count("submissions"))
        .order_by("-created_at")
    )
    return render(request, "challenges/my_challenges.html", {"challenges": challenges})


@approved_company_required
def challenge_edit(request, pk):
    challenge = _desafio_da_empresa(request, pk)
    if request.method == "POST":
        form = ChallengeForm(request.POST, instance=challenge)
        if form.is_valid():
            form.save()
            messages.success(request, "Desafio atualizado.")
            return redirect("challenges:mine")
    else:
        form = ChallengeForm(instance=challenge)

    return render(request, "challenges/create.html", {"form": form, "challenge": challenge})


@company_required
def challenge_submissions(request, pk):
    challenge = _desafio_da_empresa(request, pk)
    submissions = challenge.submissions.select_related("student", "evaluation")
    return render(
        request,
        "challenges/submissions.html",
        {"challenge": challenge, "submissions": submissions},
    )


@approved_company_required
def submission_evaluate(request, pk):
    # Só a empresa dona do desafio avalia; submissão de outro desafio devolve 404
    submission = get_object_or_404(
        Submission.objects.select_related("challenge", "student"),
        pk=pk,
        challenge__company__user=request.user,
    )
    evaluation = Evaluation.objects.filter(submission=submission).first()

    if request.method == "POST":
        form = EvaluationForm(request.POST, instance=evaluation)
        if form.is_valid():
            evaluation = form.save(commit=False)
            evaluation.submission = submission
            evaluation.evaluated_by = request.user
            evaluation.save()
            messages.success(request, "Avaliação salva. O estudante já pode ver a nota e o feedback.")
            return redirect("challenges:submissions", pk=submission.challenge.pk)
    else:
        form = EvaluationForm(instance=evaluation)

    return render(
        request,
        "challenges/evaluate.html",
        {"submission": submission, "form": form, "evaluation": evaluation},
    )


# ---------- Área do estudante ----------

@student_required
def my_submissions(request):
    submissions = request.user.submissions.select_related("challenge__company", "evaluation")
    return render(request, "challenges/my_submissions.html", {"submissions": submissions})
