import io
import re
import tarfile
from dataclasses import dataclass

import requests
from django.conf import settings

# Aceita https://github.com/owner/repo, com ou sem .git no fim, com ou sem barra final

GITHUB_URL_REGEX = re.compile(
    r"^https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

API_URL = "https://api.github.com/repos/{owner}/{repo}"
TIMEOUT_SECONDS = 3
# O download do código é maior que uma consulta e só acontece fora do envio da submissão
DOWNLOAD_TIMEOUT_SECONDS = 10
MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024
MAX_FILE_BYTES = 200_000
COMMITS_PER_PAGE = 100


class GitHubValidationResult:
    def __init__(self, valid, reason="", data=None):
        self.valid = valid
        self.reason = reason
        # Resposta da API sobre o repositório (fork, data de criação...), quando ela respondeu 200
        self.data = data


class RepoDownloadError(Exception):
    """Não foi possível consultar ou baixar o repositório. A mensagem é exibida para a empresa."""


@dataclass
class CommitHistory:
    """Resumo do histórico: só contagens e datas. Nomes e e-mails dos autores não são guardados."""
    head_sha: str
    count: int
    capped: bool  # True quando o repositório tem mais commits do que os consultados
    first_at: str
    last_at: str
    active_days: int
    authors: int


@dataclass
class RepoFile:
    path: str  # relativo à raiz do repositório
    size: int
    data: bytes | None  # None quando o arquivo passa de MAX_FILE_BYTES


def _headers():
    headers = {"Accept": "application/vnd.github+json"}
    # Sem token o GitHub aceita 60 requisições por hora por IP; com token, 5.000
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers


def parse_repo_url(url):
    """Retorna (owner, repo) se o formato bater, senão (None, None)."""
    m = GITHUB_URL_REGEX.match(url.strip())
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _api_url(url, suffix=""):
    owner, repo = parse_repo_url(url)
    if not owner:
        raise RepoDownloadError("URL não tem formato de repositório GitHub válido.")
    return API_URL.format(owner=owner, repo=repo) + suffix


def repo_exists(url):
    """
    Valida se a URL aponta pra um repositório GitHub existente.
    Fallback: se a API falhar/timeout, aceita se o formato for válido.
    """
    owner, repo = parse_repo_url(url)
    if not owner:
        return GitHubValidationResult(False, "URL não tem formato de repositório GitHub válido.")

    try:
        response = requests.get(
            API_URL.format(owner=owner, repo=repo),
            timeout=TIMEOUT_SECONDS,
            headers=_headers(),
        )
    except requests.RequestException:
        # Fallback: rede falhou, aceita pelo formato
        return GitHubValidationResult(True, "API do GitHub indisponível; validado apenas pelo formato.")

    if response.status_code == 200:
        return GitHubValidationResult(True, data=response.json())
    if response.status_code == 404:
        return GitHubValidationResult(False, "Repositório não encontrado no GitHub.")
    # Outros códigos (403 rate limit, 5xx) → fallback
    return GitHubValidationResult(True, f"GitHub respondeu {response.status_code}; validado pelo formato.")


def list_commits(url):
    """Commit mais recente e resumo do histórico, em uma única requisição (até 100 commits)."""
    try:
        response = requests.get(
            _api_url(url, "/commits"),
            params={"per_page": COMMITS_PER_PAGE},
            timeout=TIMEOUT_SECONDS,
            headers=_headers(),
        )
    except requests.RequestException as error:
        raise RepoDownloadError("Não foi possível consultar o GitHub.") from error

    # 409 é a resposta para repositório vazio
    if response.status_code != 200:
        raise RepoDownloadError(f"GitHub respondeu {response.status_code} ao consultar os commits.")

    commits = response.json()
    dates = [item["commit"]["author"]["date"] for item in commits]
    # Autor é a conta do GitHub; sem conta ligada ao commit, vale o e-mail. Assim a mesma pessoa
    # com dois e-mails configurados no git não aparece como dois autores.
    authors = {
        (item.get("author") or {}).get("login") or item["commit"]["author"]["email"].lower()
        for item in commits
    }
    return CommitHistory(
        head_sha=commits[0]["sha"],  # a API devolve do mais recente para o mais antigo
        count=len(commits),
        capped=len(commits) == COMMITS_PER_PAGE,
        first_at=min(dates),
        last_at=max(dates),
        active_days=len({date[:10] for date in dates}),
        authors=len(authors),
    )


def download_repo(url, ref=""):
    """Baixa o repositório no commit `ref` (ou no ramo padrão) e devolve (commit, arquivos).

    Uma única requisição traz o pacote .tar.gz inteiro. Ele é lido em memória, arquivo por
    arquivo, e nunca extraído em disco: assim um caminho malicioso no pacote não tem efeito."""
    try:
        response = requests.get(
            _api_url(url, f"/tarball/{ref}" if ref else "/tarball"),
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            headers=_headers(),
            stream=True,
        )
        if response.status_code == 404:
            raise RepoDownloadError("Repositório não encontrado ou privado.")
        if response.status_code != 200:
            raise RepoDownloadError(f"GitHub respondeu {response.status_code} ao baixar o repositório.")

        package = b""
        for chunk in response.iter_content(chunk_size=64 * 1024):
            package += chunk
            if len(package) > MAX_DOWNLOAD_BYTES:
                raise RepoDownloadError("Repositório grande demais para análise.")
    except requests.RequestException as error:
        raise RepoDownloadError("Não foi possível baixar o repositório do GitHub.") from error

    try:
        with tarfile.open(fileobj=io.BytesIO(package), mode="r:gz") as tar:
            # O GitHub grava o hash completo do commit no comentário do pacote
            commit_sha = tar.pax_headers.get("comment", ref)
            files = []
            for member in tar:
                # Só arquivos comuns: links simbólicos e dispositivos ficam de fora
                if not member.isfile():
                    continue
                path = member.name.split("/", 1)[-1]  # tira a pasta raiz "owner-repo-abc1234/"
                data = tar.extractfile(member).read() if member.size <= MAX_FILE_BYTES else None
                files.append(RepoFile(path=path, size=member.size, data=data))
    except tarfile.TarError as error:
        raise RepoDownloadError("O pacote do repositório veio corrompido.") from error

    return commit_sha, files
