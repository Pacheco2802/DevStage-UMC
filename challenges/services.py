"""Raio-X da entrega: registrar o commit na submissão e analisar o repositório nesse commit."""
from dataclasses import asdict

from django.utils.dateparse import parse_datetime

from integrations.github_client import RepoDownloadError, download_repo, list_commits, parse_repo_url
from integrations.repo_analysis import analyze_files

from .models import RepoSnapshot, Submission

ISSUE_TEXTS = {
    "env_file": "Há um arquivo .env versionado: ele pode conter senhas e chaves.",
    "deps_committed": "Dependências foram versionadas junto com o código (node_modules ou ambiente virtual).",
    "private_key": "Há uma chave privada dentro do repositório.",
}


def freeze_submission(submission, repo_info=None):
    """Registra o commit que está no repositório agora, com o resumo do histórico.

    Roda no envio da submissão, então faz uma única consulta curta ao GitHub e nunca falha:
    se o GitHub não responder, a entrega é aceita e o commit é registrado na análise."""
    report = {"repo": _repo_facts(repo_info), "history": {}}
    commit_sha = ""
    try:
        history = list_commits(submission.repo_url)
    except RepoDownloadError:
        pass
    else:
        commit_sha = history.head_sha
        report["history"] = asdict(history)

    return RepoSnapshot.objects.create(submission=submission, commit_sha=commit_sha, report=report)


def analyze_snapshot(snapshot):
    """Baixa o repositório no commit registrado e guarda o relatório. Análise pronta não é refeita."""
    if snapshot.status == RepoSnapshot.Status.READY:
        return snapshot

    try:
        commit_sha, files = download_repo(snapshot.submission.repo_url, ref=snapshot.commit_sha)
    except RepoDownloadError as error:
        snapshot.status = RepoSnapshot.Status.ERROR
        snapshot.error_message = str(error)
    else:
        analysis = analyze_files(files)
        if not snapshot.commit_sha:
            # O GitHub não respondeu na entrega: vale o commit desta primeira análise, e isso fica marcado
            snapshot.commit_sha = commit_sha
            analysis["commit_from_analysis"] = True
        snapshot.report = {**snapshot.report, **analysis}
        snapshot.main_language = analysis["main_language"]
        snapshot.alerts = build_alerts(snapshot)
        snapshot.status = RepoSnapshot.Status.READY
        snapshot.error_message = ""

    snapshot.save()
    return snapshot


def duplicates_of(submission):
    """Outras entregas do mesmo desafio com o mesmo repositório ou o mesmo commit."""
    key = _repo_key(submission.repo_url)
    commit_sha = getattr(getattr(submission, "snapshot", None), "commit_sha", "")
    others = (
        Submission.objects.filter(challenge=submission.challenge)
        .exclude(pk=submission.pk)
        .select_related("student", "snapshot")
    )
    return [
        other for other in others
        if _repo_key(other.repo_url) == key
        or (commit_sha and getattr(getattr(other, "snapshot", None), "commit_sha", "") == commit_sha)
    ]


def _repo_key(url):
    # Mesma URL com maiúsculas, ".git" ou barra no fim é o mesmo repositório
    owner, repo = parse_repo_url(url)
    return (owner.lower(), repo.lower()) if owner else url


def _repo_facts(repo_info):
    # repo_info é a resposta da API do GitHub na validação da URL; pode não existir (fallback)
    if not isinstance(repo_info, dict):
        return {}
    return {
        "fork": bool(repo_info.get("fork")),
        "parent": (repo_info.get("parent") or {}).get("full_name", ""),
        "created_at": repo_info.get("created_at") or "",
    }


def build_alerts(snapshot):
    """Indícios para a empresa conferir. São sinais, não vereditos: um fork pode ser legítimo."""
    report = snapshot.report
    repo = report.get("repo", {})
    history = report.get("history", {})
    alerts = [{"code": code, "text": ISSUE_TEXTS[code]} for code in report.get("issues", [])]

    if repo.get("fork"):
        origin = f" de {repo['parent']}" if repo.get("parent") else ""
        alerts.append({"code": "fork", "text": f"O repositório é um fork{origin}."})

    created_at = parse_datetime(repo.get("created_at", ""))
    if created_at and created_at < snapshot.submission.challenge.created_at:
        alerts.append({
            "code": "repo_older_than_challenge",
            "text": "O repositório foi criado antes de o desafio ser publicado.",
        })

    if history.get("count") == 1:
        alerts.append({"code": "single_commit", "text": "Todo o código foi enviado em um único commit."})

    if history.get("authors", 0) > 1:
        alerts.append({
            "code": "multiple_authors",
            "text": f"Os commits têm {history['authors']} autores diferentes.",
        })

    return alerts
