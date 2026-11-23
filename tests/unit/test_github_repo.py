"""Histórico de commits e download do repositório. O GitHub é simulado: nenhum teste usa a rede."""
import io
import tarfile
from unittest.mock import Mock, patch

import pytest
import requests

from integrations.github_client import EmptyRepoError, RepoDownloadError, download_repo, list_commits

URL = "https://github.com/pedro/devstage"
SHA = "a" * 40


def _commit(sha, data, email, login=None):
    # "author" é a conta do GitHub ligada ao commit; vem nulo quando o e-mail não pertence a nenhuma conta
    conta = {"login": login} if login else None
    return {"sha": sha, "author": conta, "commit": {"author": {"date": data, "email": email}}}


def _tarball(arquivos, sha=SHA, link=None):
    """Monta em memória um pacote igual ao do GitHub: pasta raiz com o nome do repositório."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT, pax_headers={"comment": sha}) as tar:
        for caminho, conteudo in arquivos.items():
            info = tarfile.TarInfo(f"pedro-devstage-aaaaaaa/{caminho}")
            info.size = len(conteudo)
            tar.addfile(info, io.BytesIO(conteudo))
        if link:
            info = tarfile.TarInfo(f"pedro-devstage-aaaaaaa/{link}")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
    return buffer.getvalue()


def _resposta_tarball(dados, status=200):
    return Mock(status_code=status, iter_content=lambda chunk_size: [dados])


# ---------- list_commits ----------

@patch("integrations.github_client.requests.get")
def test_deve_resumir_o_historico_sem_guardar_quem_sao_os_autores(mock_get):
    mock_get.return_value = Mock(status_code=200, json=lambda: [
        _commit("c" * 40, "2026-11-12T15:00:00Z", "Ana@x.com"),
        _commit("b" * 40, "2026-11-12T09:00:00Z", "ana@x.com"),
        _commit("d" * 40, "2026-11-10T09:00:00Z", "bia@x.com"),
    ])

    history = list_commits(URL)

    assert history.head_sha == "c" * 40
    assert history.count == 3
    assert history.capped is False
    assert history.first_at == "2026-11-10T09:00:00Z"
    assert history.last_at == "2026-11-12T15:00:00Z"
    assert history.active_days == 2
    assert history.authors == 2
    mock_get.assert_called_once_with(
        "https://api.github.com/repos/pedro/devstage/commits",
        params={"per_page": 100},
        timeout=3,
        headers={"Accept": "application/vnd.github+json"},
    )


@patch("integrations.github_client.requests.get")
def test_mesma_conta_com_dois_emails_conta_como_um_autor(mock_get):
    mock_get.return_value = Mock(status_code=200, json=lambda: [
        _commit("c" * 40, "2026-11-12T15:00:00Z", "pedro@trabalho.com", login="pedro"),
        _commit("b" * 40, "2026-11-11T15:00:00Z", "pedro@pessoal.com", login="pedro"),
    ])

    assert list_commits(URL).authors == 1


@patch("integrations.github_client.requests.get")
def test_deve_avisar_quando_ha_mais_commits_do_que_os_consultados(mock_get):
    mock_get.return_value = Mock(
        status_code=200,
        json=lambda: [_commit(f"{i:040d}", "2026-11-12T15:00:00Z", "ana@x.com") for i in range(100)],
    )

    assert list_commits(URL).capped is True


@pytest.mark.parametrize("status", [404, 409, 403, 500])
@patch("integrations.github_client.requests.get")
def test_historico_deve_falhar_quando_o_github_nao_responde_200(mock_get, status):
    mock_get.return_value = Mock(status_code=status)

    with pytest.raises(RepoDownloadError):
        list_commits(URL)


@patch("integrations.github_client.requests.get")
def test_repositorio_vazio_deve_ter_um_erro_proprio(mock_get):
    # O GitHub responde 409 quando o repositório existe mas ainda não tem nenhum commit
    mock_get.return_value = Mock(status_code=409)

    with pytest.raises(EmptyRepoError):
        list_commits(URL)


@pytest.mark.parametrize("corpo", [[], {"message": "inesperado"}, [{"sha": "abc"}]])
@patch("integrations.github_client.requests.get")
def test_historico_deve_falhar_quando_a_resposta_nao_tem_o_formato_esperado(mock_get, corpo):
    mock_get.return_value = Mock(status_code=200, json=lambda: corpo)

    with pytest.raises(RepoDownloadError):
        list_commits(URL)


@patch("integrations.github_client.requests.get")
def test_historico_deve_falhar_quando_a_rede_cai(mock_get):
    mock_get.side_effect = requests.ConnectionError()

    with pytest.raises(RepoDownloadError):
        list_commits(URL)


@patch("integrations.github_client.requests.get")
def test_deve_enviar_o_token_quando_configurado(mock_get, settings):
    settings.GITHUB_TOKEN = "token-de-teste"
    mock_get.return_value = Mock(status_code=200, json=lambda: [_commit(SHA, "2026-11-12T15:00:00Z", "a@x.com")])

    list_commits(URL)

    assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer token-de-teste"


# ---------- download_repo ----------

@patch("integrations.github_client.requests.get")
def test_deve_devolver_o_commit_e_os_arquivos_sem_a_pasta_raiz(mock_get):
    mock_get.return_value = _resposta_tarball(_tarball({"README.md": b"# Projeto", "app/main.py": b"print(1)\n"}))

    sha, files = download_repo(URL)

    assert sha == SHA
    assert [(f.path, f.data) for f in files] == [("README.md", b"# Projeto"), ("app/main.py", b"print(1)\n")]


@patch("integrations.github_client.requests.get")
def test_deve_baixar_o_commit_pedido(mock_get):
    mock_get.return_value = _resposta_tarball(_tarball({"a.py": b"x"}))

    download_repo(URL, ref="b" * 40)

    assert mock_get.call_args.args[0] == f"https://api.github.com/repos/pedro/devstage/tarball/{'b' * 40}"


@patch("integrations.github_client.requests.get")
def test_deve_ignorar_links_simbolicos(mock_get):
    mock_get.return_value = _resposta_tarball(_tarball({"a.py": b"x"}, link="segredo"))

    _, files = download_repo(URL)

    assert [f.path for f in files] == ["a.py"]


@patch("integrations.github_client.requests.get")
def test_arquivo_acima_do_limite_vem_sem_conteudo(mock_get):
    mock_get.return_value = _resposta_tarball(_tarball({"dados.csv": b"x" * 200_001}))

    _, files = download_repo(URL)

    assert files[0].size == 200_001
    assert files[0].data is None


@patch("integrations.github_client.MAX_DOWNLOAD_BYTES", 10)
@patch("integrations.github_client.requests.get")
def test_deve_recusar_repositorio_grande_demais(mock_get):
    mock_get.return_value = _resposta_tarball(_tarball({"a.py": b"x" * 500}))

    with pytest.raises(RepoDownloadError, match="grande demais"):
        download_repo(URL)


@patch("integrations.github_client.requests.get")
def test_download_deve_falhar_quando_o_repositorio_sumiu(mock_get):
    mock_get.return_value = _resposta_tarball(b"", status=404)

    with pytest.raises(RepoDownloadError, match="não encontrado"):
        download_repo(URL)


@patch("integrations.github_client.requests.get")
def test_download_deve_falhar_quando_o_pacote_vem_corrompido(mock_get):
    mock_get.return_value = _resposta_tarball(b"isto nao e um tar.gz")

    with pytest.raises(RepoDownloadError):
        download_repo(URL)


def test_download_deve_recusar_url_fora_do_formato():
    with pytest.raises(RepoDownloadError):
        download_repo("https://gitlab.com/pedro/devstage")
