from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import Http404
from django.views.decorators.http import require_POST
from .forms import SubmissionForm, ChallengeForm, EvaluationForm
from .models import Challenge, Submission, Evaluation
from .services import analyze_snapshot, duplicates_of, freeze_submission
from core.decorators import approved_company_required, company_required, student_required
from core.pagination import filtros_da_url, paginar
from integrations.github_client import EmptyRepoError

DESAFIOS_POR_PAGINA = 12
SUBMISSOES_POR_PAGINA = 20
ALREADY_SUBMITTED = "Você já enviou uma submissão para este desafio."
EMPTY_REPO = "O repositório está vazio. Envie o código para o GitHub antes de registrar a entrega."
ALREADY_EVALUATED = (
    "Esta submissão já foi avaliada. A avaliação não pode ser alterada; "
    "se houver um erro, peça a correção ao administrador da plataforma."
)


@login_required
def challenge_list(request):
    # select_related traz a empresa na mesma consulta, em vez de uma consulta por cartão (RNF11)
    challenges = (
        Challenge.objects.filter(status=Challenge.Status.OPEN).select_related("company").order_by("-created_at", "-pk")
    )
    termo = request.GET.get("q", "").strip()
    if termo:
        challenges = challenges.filter(Q(title__icontains=termo) | Q(company__company_name__icontains=termo))
    dificuldade = request.GET.get("dificuldade", "")
    if dificuldade in Challenge.Difficulty.values:
        challenges = challenges.filter(difficulty=dificuldade)
    return render(request, "challenges/list.html", {
        # Só uma página vai para a tela: com centenas de desafios, a lista inteira ficaria inutilizável
        "challenges": paginar(request, challenges, DESAFIOS_POR_PAGINA),
        "termo": termo,
        "dificuldade": dificuldade,
        "dificuldades": Challenge.Difficulty.choices,
        "filtros": filtros_da_url(request),
    })


@login_required
def challenge_detail(request, pk):
    challenge = get_object_or_404(Challenge.objects.select_related("company"), pk=pk)
    # Rascunho ainda não foi publicado: só a empresa dona enxerga
    if challenge.status == Challenge.Status.DRAFT and challenge.company.user_id != request.user.pk:
        raise Http404

    user_submission = (
        Submission.objects.filter(challenge=challenge, student=request.user)
        .select_related("evaluation")
        .first()
    )

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
            try:
                # atomic: se o banco recusar a linha, a transação da requisição continua utilizável.
                # A entrega e o registro do commit são gravados juntos ou não são gravados.
                with transaction.atomic():
                    submission.save()
                    # Registra o commit entregue: o que subir para o repositório depois não entra na avaliação
                    freeze_submission(submission, form.repo_info, reject_empty=True)
            except IntegrityError:
                # Duas requisições quase simultâneas (clique duplo, duas abas): a restrição de
                # unicidade do banco barrou a segunda, e o estudante vê a mesma mensagem da RN31
                messages.error(request, ALREADY_SUBMITTED)
                return redirect("challenges:detail", pk=pk)
            except EmptyRepoError:
                # Sem nenhum commit não há o que registrar, e o código chegaria depois do prazo (RN69)
                form.add_error("repo_url", EMPTY_REPO)
            else:
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
    if challenge.deadline_passed:
        return False, "O prazo deste desafio já venceu."
    if existing_submission is not None:
        return False, ALREADY_SUBMITTED
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
    # RN22: com a primeira entrega recebida, as condições valem igual para todos e não mudam mais
    if not challenge.is_editable:
        messages.error(request, "Este desafio já recebeu submissões ou foi encerrado e não pode mais ser editado.")
        return redirect("challenges:mine")

    if request.method == "POST":
        form = ChallengeForm(request.POST, instance=challenge)
        if form.is_valid():
            form.save()
            messages.success(request, "Desafio atualizado.")
            return redirect("challenges:mine")
    else:
        form = ChallengeForm(instance=challenge)

    return render(request, "challenges/create.html", {"form": form, "challenge": challenge})


def _mudar_situacao(request, pk, new_status, success_message):
    challenge = _desafio_da_empresa(request, pk)
    # RN21: Rascunho -> Aberto -> Encerrado, sem voltar e sem pular etapa
    if not challenge.can_transition_to(new_status):
        messages.error(
            request,
            f"Um desafio com situação {challenge.get_status_display()} não pode passar para "
            f"{Challenge.Status(new_status).label}.",
        )
    # RN19: ninguém conseguiria entregar em um desafio publicado com o prazo já vencido
    elif new_status == Challenge.Status.OPEN and challenge.deadline_passed:
        messages.error(request, "O prazo deste desafio já passou. Edite o prazo antes de publicar.")
    else:
        challenge.status = new_status
        challenge.save(update_fields=["status", "updated_at"])
        messages.success(request, success_message)
    return redirect("challenges:mine")


@approved_company_required
@require_POST
def challenge_publish(request, pk):
    return _mudar_situacao(
        request, pk, Challenge.Status.OPEN, "Desafio publicado. Ele já aparece na lista de projetos."
    )


@approved_company_required
@require_POST
def challenge_close(request, pk):
    return _mudar_situacao(
        request, pk, Challenge.Status.CLOSED, "Desafio encerrado. As submissões já podem ser avaliadas."
    )


@company_required
def challenge_submissions(request, pk):
    challenge = _desafio_da_empresa(request, pk)
    submissions = challenge.submissions.select_related("student", "evaluation")
    return render(
        request,
        "challenges/submissions.html",
        {"challenge": challenge, "submissions": paginar(request, submissions, SUBMISSOES_POR_PAGINA)},
    )


def _check_can_evaluate(challenge, existing_evaluation):
    """Devolve o motivo do bloqueio, ou "" quando a empresa pode avaliar."""
    # RN44: uma avaliação por submissão, sem alteração pela empresa
    if existing_evaluation is not None:
        return ALREADY_EVALUATED
    # RN41: todos são avaliados nas mesmas condições, depois que ninguém mais pode entregar
    if not challenge.accepts_evaluation:
        return "A avaliação só é liberada depois do prazo ou do encerramento do desafio."
    return ""


@approved_company_required
def submission_evaluate(request, pk):
    # Só a empresa dona do desafio avalia; submissão de outro desafio devolve 404
    submission = get_object_or_404(
        Submission.objects.select_related("challenge", "student"),
        pk=pk,
        challenge__company__user=request.user,
    )
    evaluation = Evaluation.objects.filter(submission=submission).first()
    block_reason = _check_can_evaluate(submission.challenge, evaluation)
    form = None

    if request.method == "POST":
        if block_reason:
            messages.error(request, block_reason)
            return redirect("challenges:evaluate", pk=pk)

        form = EvaluationForm(request.POST)
        if form.is_valid():
            evaluation = form.save(commit=False)
            evaluation.submission = submission
            evaluation.evaluated_by = request.user
            try:
                with transaction.atomic():
                    evaluation.save()  # os pontos são calculados no save (RF13)
            except IntegrityError:
                # Dois envios quase simultâneos: a relação um para um do banco barrou o segundo
                messages.error(request, ALREADY_EVALUATED)
                return redirect("challenges:evaluate", pk=pk)
            messages.success(
                request,
                f"Avaliação salva: {evaluation.points} pontos. O estudante já pode ver a nota e o feedback.",
            )
            return redirect("challenges:submissions", pk=submission.challenge.pk)
    elif not block_reason:
        form = EvaluationForm()

    return render(
        request,
        "challenges/evaluate.html",
        {
            "form": form,
            "evaluation": evaluation,
            "block_reason": block_reason,
            **_snapshot_context(submission),
        },
    )


def _snapshot_context(submission):
    return {
        "submission": submission,
        "snapshot": getattr(submission, "snapshot", None),
        "duplicates": duplicates_of(submission),
    }


@approved_company_required
@require_POST
def submission_snapshot(request, pk):
    """Raio-X da entrega, pedido pela tela de avaliação via HTMX: analisa o repositório no
    commit registrado e devolve só o painel. Entrega antiga, sem registro, é registrada agora."""
    submission = get_object_or_404(
        Submission.objects.select_related("challenge", "student"),
        pk=pk,
        challenge__company__user=request.user,
    )
    snapshot = getattr(submission, "snapshot", None) or freeze_submission(submission)
    analyze_snapshot(snapshot)
    return render(request, "challenges/_snapshot.html", _snapshot_context(submission))


# ---------- Área do estudante ----------

@student_required
def my_submissions(request):
    submissions = request.user.submissions.select_related("challenge__company", "evaluation", "snapshot")
    return render(request, "challenges/my_submissions.html", {"submissions": submissions})
