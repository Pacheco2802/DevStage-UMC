"""Raio-X de um repositório a partir da lista de arquivos.

Função pura: não usa rede nem banco, só lê os arquivos que o github_client baixou.
O resultado é um dicionário simples, guardado em RepoSnapshot.report."""
import json
import re
from pathlib import PurePosixPath

LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".c": "C", ".h": "C", ".cpp": "C++", ".rs": "Rust", ".swift": "Swift", ".dart": "Dart",
    ".vue": "Vue", ".sql": "SQL", ".html": "HTML", ".css": "CSS", ".scss": "CSS",
}
# Marcação só vira "linguagem principal" quando o repositório não tem outra
MARKUP = ["HTML", "CSS"]

# Pastas que não são código do estudante
DEPENDENCY_DIRS = ["node_modules", "venv", ".venv", "site-packages"]
IGNORED_DIRS = DEPENDENCY_DIRS + ["dist", "build", "vendor", "target", "__pycache__", ".git", ".idea", ".vscode"]

TEST_DIRS = ["tests", "test", "__tests__", "spec"]
README_MIN_CHARS = 300

# Dependência (como aparece no manifesto) -> nome exibido
KNOWN_DEPENDENCIES = {
    "django": "Django", "djangorestframework": "Django REST", "flask": "Flask", "fastapi": "FastAPI",
    "pytest": "pytest", "sqlalchemy": "SQLAlchemy", "pandas": "pandas",
    "react": "React", "next": "Next.js", "vue": "Vue", "@angular/core": "Angular", "express": "Express",
    "@nestjs/core": "NestJS", "tailwindcss": "Tailwind CSS", "jest": "Jest", "prisma": "Prisma",
    "laravel/framework": "Laravel", "rails": "Rails", "spring-boot-starter": "Spring Boot",
    "spring-boot-starter-web": "Spring Boot",
}
TEXT_MANIFESTS = [
    "requirements.txt", "pyproject.toml", "Pipfile", "pom.xml", "build.gradle", "Gemfile", "composer.json",
]
TOKEN = re.compile(r"[a-z0-9@/_.-]+")


def analyze_files(files):
    code = [f for f in files if _language(f) and not _inside(f, IGNORED_DIRS)]
    lines_by_language = {}
    for f in code:
        lines_by_language[_language(f)] = lines_by_language.get(_language(f), 0) + _lines(f)

    total = sum(lines_by_language.values())
    ranking = sorted(lines_by_language.items(), key=lambda item: -item[1])
    languages = [{"name": name, "percent": round(100 * lines / total)} for name, lines in ranking if total]
    real_languages = [name for name, _ in ranking if name not in MARKUP]

    return {
        "languages": languages,
        "main_language": (real_languages or [name for name, _ in ranking] or [""])[0],
        "files": len(code),
        "lines": total,
        "readme": _readme(files),
        "test_files": sum(1 for f in code if _is_test(f)),
        "practices": _practices(files),
        "stack": _stack(files),
        "issues": _issues(files),
    }


def _parts(f):
    return PurePosixPath(f.path).parts


def _inside(f, folders):
    return any(part in folders for part in _parts(f)[:-1])


def _language(f):
    return LANGUAGES.get(PurePosixPath(f.path).suffix.lower())


def _lines(f):
    return len(f.data.splitlines()) if f.data else 0


def _text(f):
    return f.data.decode("utf-8", errors="replace") if f.data else ""


def _readme(files):
    readme = next((f for f in files if len(_parts(f)) == 1 and f.path.lower().startswith("readme")), None)
    if readme is None:
        return "ausente"
    return "ok" if len(_text(readme).strip()) >= README_MIN_CHARS else "minimo"


def _is_test(f):
    name = PurePosixPath(f.path).name
    stem = name.split(".")[0]
    return (
        _inside(f, TEST_DIRS)
        or stem.startswith("test_")
        or stem.endswith(("_test", "Test", "Tests"))
        or ".test." in name
        or ".spec." in name
    )


def _practices(files):
    paths = [f.path for f in files]
    names = [PurePosixPath(path).name.lower() for path in paths]
    found = {
        "gitignore": ".gitignore" in paths,
        "license": any(len(PurePosixPath(p).parts) == 1 and p.lower().startswith("licen") for p in paths),
        "docker": any(name in ["dockerfile", "docker-compose.yml", "compose.yaml"] for name in names),
        "ci": any(p.startswith(".github/workflows/") or p == ".gitlab-ci.yml" for p in paths),
        "env_example": any(name in [".env.example", ".env.sample"] for name in names),
    }
    return [practice for practice, present in found.items() if present]


def _stack(files):
    dependencies = set()
    for f in files:
        if _inside(f, IGNORED_DIRS):
            continue
        name = PurePosixPath(f.path).name
        if name == "package.json":
            dependencies |= _package_json_dependencies(_text(f))
        elif name in TEXT_MANIFESTS:
            dependencies |= set(TOKEN.findall(_text(f).lower()))
    return sorted({label for dep, label in KNOWN_DEPENDENCIES.items() if dep in dependencies}, key=str.lower)


def _package_json_dependencies(text):
    # Só as chaves de dependências: um script chamado "express" não é uma dependência
    try:
        package = json.loads(text)
        return set(package.get("dependencies", {})) | set(package.get("devDependencies", {}))
    except (ValueError, AttributeError, TypeError):
        return set()


def _issues(files):
    issues = []
    for f in files:
        name = PurePosixPath(f.path).name.lower()
        in_dependencies = _inside(f, DEPENDENCY_DIRS)
        is_env = name == ".env" or (name.startswith(".env.") and not name.endswith(("example", "sample", "template")))
        if is_env and not in_dependencies:
            issues.append("env_file")
        if in_dependencies:
            issues.append("deps_committed")
        if f.data and b"PRIVATE KEY-----" in f.data and not in_dependencies:
            issues.append("private_key")
    return sorted(set(issues))
