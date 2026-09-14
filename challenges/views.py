from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import SubmissionForm
from .models import Challenge, Submission


@login_required
def challenge_list(request):
    challenges = Challenge.objects.filter(status=Challenge.Status.OPEN)
    return render(request, "challenges/list.html", {"challenges": challenges})


@login_required
def challenge_detail(request, pk):
    challenge = get_object_or_404(Challenge, pk=pk)

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
