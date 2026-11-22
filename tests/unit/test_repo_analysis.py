"""Análise dos arquivos de um repositório: função pura, sem rede e sem banco."""
from integrations.github_client import RepoFile
from integrations.repo_analysis import analyze_files


def _arquivo(path, texto=""):
    dados = texto.encode()
    return RepoFile(path=path, size=len(dados), data=dados)


def _linhas(quantidade):
    return "x = 1\n" * quantidade


# ---------- Linguagens e tamanho ----------

def test_deve_calcular_o_percentual_de_cada_linguagem_pelas_linhas():
    report = analyze_files([_arquivo("app/main.py", _linhas(30)), _arquivo("web/app.js", _linhas(10))])

    assert report["languages"] == [{"name": "Python", "percent": 75}, {"name": "JavaScript", "percent": 25}]
    assert report["main_language"] == "Python"
    assert report["files"] == 2
    assert report["lines"] == 40


def test_marcacao_so_e_linguagem_principal_quando_nao_ha_outra():
    com_python = analyze_files([_arquivo("templates/base.html", _linhas(100)), _arquivo("app.py", _linhas(10))])
    so_html = analyze_files([_arquivo("index.html", _linhas(100)), _arquivo("style.css", _linhas(10))])

    assert com_python["languages"][0]["name"] == "HTML"
    assert com_python["main_language"] == "Python"
    assert so_html["main_language"] == "HTML"


def test_dependencias_versionadas_nao_contam_como_codigo_e_viram_problema():
    report = analyze_files([_arquivo("app.js", _linhas(10)), _arquivo("node_modules/lib/index.js", _linhas(5000))])

    assert report["files"] == 1
    assert report["lines"] == 10
    assert "deps_committed" in report["issues"]


def test_arquivo_grande_demais_conta_como_arquivo_sem_linhas():
    report = analyze_files([RepoFile(path="dados.py", size=900_000, data=None)])

    assert report["files"] == 1
    assert report["lines"] == 0


def test_repositorio_sem_codigo_devolve_relatorio_vazio():
    report = analyze_files([_arquivo("foto.png", "binario")])

    assert report["files"] == 0
    assert report["languages"] == []
    assert report["main_language"] == ""


# ---------- README, testes e boas práticas ----------

def test_deve_classificar_o_readme():
    ausente = analyze_files([_arquivo("app.py", "x")])
    minimo = analyze_files([_arquivo("readme.MD", "# Projeto")])
    completo = analyze_files([_arquivo("README.md", "Como rodar o projeto. " * 20)])
    fora_da_raiz = analyze_files([_arquivo("docs/README.md", "Como rodar o projeto. " * 20)])

    assert ausente["readme"] == "ausente"
    assert minimo["readme"] == "minimo"
    assert completo["readme"] == "ok"
    assert fora_da_raiz["readme"] == "ausente"


def test_deve_contar_arquivos_de_teste_por_pasta_e_por_nome():
    report = analyze_files([
        _arquivo("tests/test_pedidos.py", "x"),
        _arquivo("src/carrinho.test.js", "x"),
        _arquivo("src/main/PedidoTest.java", "x"),
        _arquivo("src/contest.py", "x"),
    ])

    assert report["test_files"] == 3


def test_deve_listar_as_boas_praticas_presentes():
    report = analyze_files([
        _arquivo(".gitignore", "venv"),
        _arquivo("LICENSE", "MIT"),
        _arquivo("Dockerfile", "FROM python"),
        _arquivo(".github/workflows/ci.yml", "on: push"),
        _arquivo(".env.example", "DEBUG=True"),
    ])

    assert report["practices"] == ["gitignore", "license", "docker", "ci", "env_example"]


# ---------- Tecnologias ----------

def test_deve_detectar_tecnologias_pelo_requirements():
    report = analyze_files([_arquivo("requirements.txt", "Django==5.2.17\npytest>=9\nrequests\n")])

    assert report["stack"] == ["Django", "pytest"]


def test_deve_detectar_tecnologias_pelo_package_json_sem_confundir_scripts():
    package = (
        '{"scripts": {"express": "node x"}, "dependencies": {"react": "^19", "next": "15"},'
        ' "devDependencies": {"jest": "30"}}'
    )
    report = analyze_files([_arquivo("frontend/package.json", package)])

    assert report["stack"] == ["Jest", "Next.js", "React"]


def test_package_json_invalido_nao_derruba_a_analise():
    report = analyze_files([_arquivo("package.json", "{ isto não é json")])

    assert report["stack"] == []


# ---------- Problemas ----------

def test_deve_apontar_env_versionado_mas_nao_o_exemplo():
    com_env = analyze_files([_arquivo(".env", "SECRET_KEY=abc")])
    so_exemplo = analyze_files([_arquivo(".env.example", "SECRET_KEY=")])

    assert "env_file" in com_env["issues"]
    assert "env_file" not in so_exemplo["issues"]


def test_deve_apontar_chave_privada_no_repositorio():
    report = analyze_files([_arquivo("deploy/id_rsa", "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n")])

    assert "private_key" in report["issues"]
