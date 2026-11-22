"""Teste de carga do DevStage: usuários virtuais navegando ao mesmo tempo.

Cada usuário virtual é uma thread que entra no sistema e fica abrindo páginas, com uma pausa
entre uma e outra, como uma pessoa faria. O teste roda em etapas, cada uma com mais usuários
simultâneos, e mede o tempo de resposta de cada requisição.

Uso (a senha das contas vem de uma variável de ambiente, para não ficar no histórico do terminal):

    set CARGA_SENHA=<senha das contas de demonstração>
    python tests/load/carga.py --base http://localhost:8000 --contas msato,cferraz,lprado

Opções: --usuarios 10,25,50 (etapas), --duracao 60 (segundos por etapa), --rampa 20 (segundos em
que os usuários vão entrando), --aquecimento 10,
--saida relatorio.md.
Com mais de um --base, os usuários são distribuídos entre os endereços.

Só faz leituras (GET) e o login: não cria submissões nem avaliações, então pode ser repetido
sem sujar a base. Depende apenas da biblioteca requests, que o projeto já usa.
"""
import argparse
import os
import random
import re
import statistics
import threading
import time
from dataclasses import dataclass, field

import requests

PAUSA_ENTRE_PAGINAS = [0.5, 1.5]  # segundos, sorteados a cada página
TEMPO_LIMITE = 30


@dataclass
class Medida:
    pagina: str
    segundos: float
    ok: bool


@dataclass
class Etapa:
    usuarios: int
    duracao: float
    medidas: list = field(default_factory=list)


class UsuarioVirtual:
    """Navega como um estudante autenticado ou, sem conta, como um visitante."""

    def __init__(self, base, conta, senha, medidas, parar):
        self.base, self.conta, self.senha = base.rstrip("/"), conta, senha
        self.medidas, self.parar = medidas, parar
        # Os cookies são guardados à mão: com DEBUG desligado eles vêm marcados como "Secure",
        # e uma biblioteca HTTP comum se recusaria a devolvê-los em um teste local por http://
        self.cookies = {}
        self.desafios, self.estudantes = [], []

    # ---------- HTTP ----------
    def pedir(self, pagina, metodo, caminho, **kwargs):
        headers = {"Cookie": "; ".join(f"{nome}={valor}" for nome, valor in self.cookies.items())}
        inicio = time.perf_counter()
        try:
            resposta = requests.request(
                metodo, self.base + caminho, headers=headers, timeout=TEMPO_LIMITE, allow_redirects=False, **kwargs
            )
            ok = resposta.status_code < 400
            self.cookies.update(resposta.cookies.get_dict())
        except requests.RequestException:
            resposta, ok = None, False
        self.medidas.append(Medida(pagina, time.perf_counter() - inicio, ok))
        return resposta

    def entrar(self):
        self.pedir("tela de login", "GET", "/accounts/login/")
        resposta = self.pedir("login (POST)", "POST", "/accounts/login/", data={
            "username": self.conta, "password": self.senha, "csrfmiddlewaretoken": self.cookies.get("csrftoken", ""),
        })
        return resposta is not None and resposta.status_code == 302 and "sessionid" in self.cookies

    # ---------- Páginas ----------
    def lista_de_desafios(self):
        resposta = self.pedir("lista de desafios", "GET", "/challenges/")
        if resposta is not None:
            self.desafios = re.findall(r'href="/challenges/(\d+)/"', resposta.text) or self.desafios

    def detalhe_do_desafio(self):
        if self.desafios:
            self.pedir("detalhe do desafio", "GET", f"/challenges/{random.choice(self.desafios)}/")

    def ranking(self):
        resposta = self.pedir("ranking", "GET", "/portfolio/ranking/")
        if resposta is not None:
            nomes = set(re.findall(r'href="/portfolio/([\w.@+-]+)/"', resposta.text)) - {"ranking", "meu-perfil"}
            self.estudantes = sorted(nomes) or self.estudantes

    def portfolio(self):
        if self.estudantes:
            self.pedir("portfólio", "GET", f"/portfolio/{random.choice(self.estudantes)}/")

    def minhas_submissoes(self):
        self.pedir("minhas submissões", "GET", "/challenges/minhas-submissoes/")

    def dashboard(self):
        self.pedir("dashboard", "GET", "/dashboard/")
        self.pedir("dashboard (API JSON)", "GET", "/dashboard/api/dados/")

    def meus_dados(self):
        self.pedir("meus dados", "GET", "/accounts/meus-dados/")

    # ---------- Roteiro ----------
    def navegar(self):
        if self.conta:
            if not self.entrar():
                return
            # pesos: o que um estudante mais abre é a lista, um desafio e o ranking
            roteiro = [
                [self.lista_de_desafios, 30], [self.detalhe_do_desafio, 20], [self.ranking, 15], [self.portfolio, 15],
                [self.minhas_submissoes, 10], [self.dashboard, 7], [self.meus_dados, 3],
            ]
            self.lista_de_desafios()
        else:
            roteiro = [[self.ranking, 50], [self.portfolio, 50]]  # visitante: só as páginas públicas
            self.ranking()
        paginas, pesos = [item[0] for item in roteiro], [item[1] for item in roteiro]
        while not self.parar.is_set():
            self.parar.wait(random.uniform(*PAUSA_ENTRE_PAGINAS))
            if not self.parar.is_set():
                random.choices(paginas, weights=pesos)[0]()


def rodar_etapa(bases, contas, senha, usuarios, duracao, visitantes, rampa=0):
    etapa = Etapa(usuarios, duracao)
    parar = threading.Event()
    threads = []
    for numero in range(usuarios):
        # uma parte dos usuários é visitante, sem conta
        conta = "" if numero < usuarios * visitantes else contas[numero % len(contas)]
        usuario = UsuarioVirtual(bases[numero % len(bases)], conta, senha, etapa.medidas, parar)
        threads.append(threading.Thread(target=usuario.navegar, daemon=True))
    inicio = time.perf_counter()
    for thread in threads:
        thread.start()
        # Os usuários entram aos poucos, e não todos no mesmo instante, como aconteceria de verdade
        time.sleep(rampa / usuarios)
    time.sleep(max(0, duracao - rampa))
    parar.set()
    for thread in threads:
        thread.join(TEMPO_LIMITE + 5)
    etapa.duracao = time.perf_counter() - inicio
    return etapa


def percentil(valores, p):
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(len(ordenados) * p / 100))]


def resumo(medidas, duracao):
    tempos = [medida.segundos * 1000 for medida in medidas]
    erros = sum(1 for medida in medidas if not medida.ok)
    return {
        "requisicoes": len(medidas), "erros": erros, "por_segundo": len(medidas) / duracao,
        "mediana": statistics.median(tempos), "p95": percentil(tempos, 95), "p99": percentil(tempos, 99), "maximo": max(tempos),
    }


def relatorio(etapas):
    linhas = [
        "| Usuários simultâneos | Requisições | Erros | Req./s | Mediana (ms) | p95 (ms) | p99 (ms) | Máximo (ms) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for etapa in etapas:
        r = resumo(etapa.medidas, etapa.duracao)
        linhas.append(
            f"| {etapa.usuarios} | {r['requisicoes']} | {r['erros']} | {r['por_segundo']:.1f} | {r['mediana']:.0f} | "
            f"{r['p95']:.0f} | {r['p99']:.0f} | {r['maximo']:.0f} |"
        )
    linhas += ["", "Por página, na etapa com mais usuários:", "",
               "| Página | Requisições | Erros | Mediana (ms) | p95 (ms) | Máximo (ms) |", "|---|---:|---:|---:|---:|---:|"]
    ultima = etapas[-1]
    for pagina in sorted({medida.pagina for medida in ultima.medidas}):
        r = resumo([medida for medida in ultima.medidas if medida.pagina == pagina], ultima.duracao)
        linhas.append(f"| {pagina} | {r['requisicoes']} | {r['erros']} | {r['mediana']:.0f} | {r['p95']:.0f} | {r['maximo']:.0f} |")
    return "\n".join(linhas)


def main():
    parser = argparse.ArgumentParser(description="Teste de carga do DevStage")
    parser.add_argument("--base", action="append", required=True, help="endereço do sistema; pode ser repetido")
    parser.add_argument("--contas", required=True, help="nomes de usuário de estudantes, separados por vírgula")
    parser.add_argument("--usuarios", default="10,25,50", help="usuários simultâneos de cada etapa")
    parser.add_argument("--duracao", type=float, default=60, help="segundos de cada etapa")
    parser.add_argument("--visitantes", type=float, default=0.2, help="fração dos usuários que navega sem conta")
    parser.add_argument("--rampa", type=float, default=20, help="segundos, dentro da etapa, em que os usuários vão entrando")
    parser.add_argument("--aquecimento", type=float, default=10, help="segundos de aquecimento, que não entram no relatório")
    parser.add_argument("--saida", help="arquivo onde gravar o relatório em Markdown")
    args = parser.parse_args()

    senha = os.environ.get("CARGA_SENHA", "")
    if not senha:
        raise SystemExit("Defina a variável de ambiente CARGA_SENHA com a senha das contas usadas no teste.")

    contas = args.contas.split(",")
    if args.aquecimento:
        # As primeiras requisições de cada processo são mais lentas (carga de módulos, conexão com o banco)
        print(f"Aquecimento por {args.aquecimento:.0f} s...", flush=True)
        rodar_etapa(args.base, contas, senha, 2 * len(args.base), args.aquecimento, 0)

    etapas = []
    for usuarios in [int(valor) for valor in args.usuarios.split(",")]:
        print(f"Etapa com {usuarios} usuários simultâneos por {args.duracao:.0f} s...", flush=True)
        etapas.append(rodar_etapa(args.base, contas, senha, usuarios, args.duracao, args.visitantes, args.rampa))
    texto = relatorio(etapas)
    print(texto)
    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto + "\n")


if __name__ == "__main__":
    main()
