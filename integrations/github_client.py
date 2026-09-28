import re
import requests

# Aceita https://github.com/owner/repo, com ou sem .git no fim, com ou sem barra final

GITHUB_URL_REGEX = re.compile(
    r"^https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

API_URL = "https://api.github.com/repos/{owner}/{repo}"
TIMEOUT_SECONDS = 3

class GitHubValidationResult:
    def __init__(self, valid, reason=""):
        self.valid = valid
        self.reason = reason

def parse_repo_url(url):
    """Retorna (owner, repo) se o formato bater, senão (None, None)."""
    m = GITHUB_URL_REGEX.match(url.strip())
    if not m:
        return None, None
    return m.group(1), m.group(2)

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
            headers={"Accept": "application/vnd.github+json"},
        )
    except requests.RequestException:
        # Fallback: rede falhou, aceita pelo formato
        return GitHubValidationResult(True, "API do GitHub indisponível; validado apenas pelo formato.")

    if response.status_code == 200:
        return GitHubValidationResult(True)
    if response.status_code == 404:
        return GitHubValidationResult(False, "Repositório não encontrado no GitHub.")
    # Outros códigos (403 rate limit, 5xx) → fallback
    return GitHubValidationResult(True, f"GitHub respondeu {response.status_code}; validado pelo formato.")