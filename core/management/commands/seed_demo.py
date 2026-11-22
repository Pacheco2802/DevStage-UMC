"""Popula o banco com dados fictícios de demonstração.

Uso:
    SEED_DEMO_PASSWORD=<senha> python manage.py seed_demo      # cria os dados
    python manage.py seed_demo --limpar                         # remove só os dados de demonstração

Toda conta criada aqui usa um e-mail do domínio reservado DOMINIO_DEMO. É essa marca que
permite encontrar e apagar depois apenas o que é demonstração, sem tocar em contas reais.
"""
import hashlib
import os
import random
import unicodedata
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import CompanyProfile, ConsentLog, StudentProfile, TermsVersion
from challenges.models import Challenge, Evaluation, RepoSnapshot, Submission
from challenges.services import build_alerts

User = get_user_model()

DOMINIO_DEMO = "demo.devstage.test"
VARIAVEL_SENHA = "SEED_DEMO_PASSWORD"
TAMANHO_MINIMO_SENHA = 8

# (usuário, nome da empresa, aprovada pelo administrador?)
EMPRESAS = [
    ["nimbo", "Nimbo Sistemas", True],
    ["voltedge", "VoltEdge Energia", True],
    ["mercadinho", "Mercadinho Digital", False],
]

# publicado_ha e prazo_em são dias contados a partir de hoje (prazo negativo = já venceu).
# Só recebem avaliação os desafios encerrados ou com o prazo vencido, como exige a regra do sistema.
DESAFIOS = [
    {
        "empresa": "nimbo", "slug": "agenda-vet-api", "status": Challenge.Status.OPEN,
        "dificuldade": Challenge.Difficulty.INTERMEDIATE,
        "publicado_ha": 24, "prazo_em": 18,
        "titulo": "API de agendamento para clínica veterinária",
        "descricao": (
            "Construa uma API para cadastrar tutores, pets e consultas, com regras de conflito de "
            "horário e documentação dos endpoints.\n\n"
            "Entregue o repositório com instruções de execução e testes automatizados das regras principais."
        ),
    },
    {
        "empresa": "nimbo", "slug": "encurtador-links", "status": Challenge.Status.CLOSED,
        "dificuldade": Challenge.Difficulty.BEGINNER,
        "publicado_ha": 30, "prazo_em": -6,
        "titulo": "Encurtador de links com estatísticas de acesso",
        "descricao": (
            "Crie um encurtador de URLs que registre os acessos por dia e mostre um resumo por link.\n\n"
            "Vale qualquer linguagem. O que conta é a clareza do código e o tratamento de links inválidos."
        ),
    },
    {
        "empresa": "nimbo", "slug": "importador-nfe", "status": Challenge.Status.CLOSED,
        "dificuldade": Challenge.Difficulty.ADVANCED,
        "publicado_ha": 40, "prazo_em": -4,
        "titulo": "Importador de notas fiscais em XML",
        "descricao": (
            "Leia arquivos XML de NF-e, valide os campos obrigatórios e gere um relatório de inconsistências.\n\n"
            "Inclua pelo menos três arquivos de exemplo: um válido e dois com erros diferentes."
        ),
    },
    {
        "empresa": "nimbo", "slug": "lista-tarefas", "status": Challenge.Status.DRAFT,
        "dificuldade": Challenge.Difficulty.BEGINNER,
        "publicado_ha": 2, "prazo_em": 45,
        "titulo": "Aplicativo de lista de tarefas com lembretes",
        "descricao": "Rascunho: a empresa ainda está definindo o escopo deste desafio.",
    },
    {
        "empresa": "voltedge", "slug": "painel-energia", "status": Challenge.Status.OPEN,
        "dificuldade": Challenge.Difficulty.INTERMEDIATE,
        "publicado_ha": 26, "prazo_em": -2,
        "titulo": "Painel de consumo de energia por setor",
        "descricao": (
            "A partir de uma planilha de leituras, monte um painel que mostre o consumo por setor e "
            "destaque picos fora do padrão.\n\n"
            "Explique no README como você definiu o que é um pico."
        ),
    },
    {
        "empresa": "voltedge", "slug": "simulador-conta-luz", "status": Challenge.Status.OPEN,
        "dificuldade": Challenge.Difficulty.BEGINNER,
        "publicado_ha": 8, "prazo_em": 35,
        "titulo": "Simulador de conta de luz por bandeira tarifária",
        "descricao": (
            "Dado o consumo em kWh e a bandeira do mês, calcule o valor da conta e compare os "
            "últimos seis meses.\n\n"
            "As tarifas devem ficar em um arquivo de configuração, não espalhadas pelo código."
        ),
    },
    {
        "empresa": "voltedge", "slug": "coletor-leituras", "status": Challenge.Status.CLOSED,
        "dificuldade": Challenge.Difficulty.INTERMEDIATE,
        "publicado_ha": 38, "prazo_em": -9,
        "titulo": "Coletor de leituras de medidores via CSV",
        "descricao": (
            "Importe leituras de medidores a partir de arquivos CSV, rejeite linhas duplicadas e "
            "registre o motivo de cada linha recusada."
        ),
    },
]

ESTUDANTES = [
    "Marina Sato", "Caio Ferraz", "Letícia Prado", "Bruno Tavares", "Isabela Rocha", "Thiago Moura",
    "Camila Duarte", "Lucas Pimentel", "Aline Barros", "Gustavo Lins", "Renata Kato", "Felipe Arantes",
    "Júlia Moreira", "Rafael Nunes", "Vinícius Teles", "Larissa Campos", "Diego Faria", "Natália Reis",
    "Pedro Antunes", "Sofia Guerra", "André Bastos", "Bianca Leal", "Mateus Coelho", "Helena Vaz",
]

NOTAS_DO_ESTUDANTE = [
    "Usei Django com testes em pytest. As decisões de arquitetura estão no README.",
    "Separei as regras de negócio das views e documentei os endpoints. Faltou tempo para o deploy.",
    "Projeto em camadas, com validação nas entradas. Os casos de erro estão cobertos por testes.",
    "Comecei pelos testes das regras principais e só depois fiz a interface. Detalhes no README.",
]

PONTOS_FORTES = [
    "Código bem organizado, com testes cobrindo as regras principais.",
    "Boa separação em camadas e README claro, com instruções de execução.",
    "Solução enxuta e bem documentada. O deploy funcionou de primeira.",
    "Os commits contam a história do projeto e as decisões estão explicadas.",
    "Bom domínio do problema e tratamento cuidadoso das entradas inválidas.",
    "Entrega funcional, que cumpre tudo o que o desafio pedia.",
]

PONTOS_A_MELHORAR = [
    "Faltou tratar entradas duplicadas e documentar os casos de erro.",
    "Vale revisar os nomes das variáveis e quebrar as funções mais longas.",
    "A lógica de negócio está misturada com as views; separe em uma camada própria.",
    "As mensagens de erro poderiam ser mais claras para quem usa o sistema.",
    "Adicione testes automatizados para os casos de erro, não só para o caminho feliz.",
    "O README não explica como rodar os testes nem as variáveis de ambiente.",
]

APRESENTACOES = [
    "Estudante de Engenharia de Software. Gosto de back-end, bancos de dados e de código com testes.",
    "Curso Análise e Desenvolvimento de Sistemas e estou em busca do primeiro estágio em desenvolvimento web.",
    "Interesse em APIs, automação e dados. Aprendo melhor construindo projetos do início ao fim.",
    "",
]


# Perfis de repositório para o raio-X de demonstração: linguagem principal, percentuais e tecnologias
PERFIS_RAIO_X = [
    ["Python", [["Python", 78], ["HTML", 22]], ["Django", "pytest"]],
    ["JavaScript", [["JavaScript", 85], ["CSS", 15]], ["Express", "Jest"]],
    ["TypeScript", [["TypeScript", 90], ["CSS", 10]], ["Next.js", "React", "Tailwind CSS"]],
    ["Java", [["Java", 100]], ["Spring Boot"]],
]

PRATICAS_RAIO_X = ["gitignore", "license", "docker", "ci", "env_example"]


def gerar_username(nome_completo):
    """'Letícia Prado' -> 'lprado' (inicial do nome + sobrenome, sem acentos)."""
    sem_acentos = unicodedata.normalize("NFKD", nome_completo).encode("ascii", "ignore").decode()
    nome, sobrenome = sem_acentos.lower().split(" ", 1)
    return nome[0] + sobrenome.replace(" ", "")


class Command(BaseCommand):
    help = "Cria dados fictícios de demonstração (empresas, desafios, estudantes, submissões e avaliações)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Remove as contas de demonstração e tudo que depende delas, em vez de criar.",
        )

    def handle(self, *args, **options):
        if options["limpar"]:
            self.limpar()
            return

        if self.contas_demo().exists():
            self.stdout.write(self.style.WARNING(
                "Os dados de demonstração já existem. Rode com --limpar antes de criar de novo."
            ))
            return

        senha = os.environ.get(VARIAVEL_SENHA, "")
        if len(senha) < TAMANHO_MINIMO_SENHA:
            raise CommandError(
                f"Defina a variável de ambiente {VARIAVEL_SENHA} com a senha das contas de "
                f"demonstração (mínimo de {TAMANHO_MINIMO_SENHA} caracteres)."
            )

        with transaction.atomic():
            resumo = self.criar(senha)

        self.stdout.write(self.style.SUCCESS(
            "Dados de demonstração criados: {empresas} empresas, {desafios} desafios, {estudantes} estudantes, "
            "{submissoes} submissões e {avaliacoes} avaliações.".format(**resumo)
        ))
        self.stdout.write("Empresas: " + ", ".join(resumo["logins_empresas"]))
        self.stdout.write("Estudantes: " + ", ".join(resumo["logins_estudantes"]))

    # ---------- consulta e limpeza ----------

    def contas_demo(self):
        return User.objects.filter(email__endswith="@" + DOMINIO_DEMO)

    def limpar(self):
        contas = self.contas_demo()
        total = contas.count()
        # Apagar a conta leva junto perfil de empresa, desafios, submissões e avaliações (on_delete=CASCADE)
        contas.delete()
        self.stdout.write(self.style.SUCCESS(f"{total} contas de demonstração removidas, com tudo que dependia delas."))

    # ---------- criação ----------

    def criar(self, senha):
        # Semente fixa: o sorteio é o mesmo em toda execução, então os dados saem sempre iguais
        sorteio = random.Random(2026)
        agora = timezone.now()

        empresas = self.criar_empresas(senha)
        desafios = self.criar_desafios(empresas, agora)
        estudantes = self.criar_estudantes(senha)
        submissoes, avaliacoes = self.criar_submissoes(estudantes, desafios, sorteio, agora)

        return {
            "empresas": len(empresas),
            "desafios": len(desafios),
            "estudantes": len(estudantes),
            "submissoes": submissoes,
            "avaliacoes": avaliacoes,
            "logins_empresas": [perfil.user.username for perfil in empresas.values()],
            "logins_estudantes": [aluno.username for aluno in estudantes],
        }

    def criar_conta(self, username, senha, role, **extras):
        """Cria a conta com o aceite dos termos. Devolve None se o usuário já existe (conta real)."""
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"Usuário '{username}' já existe e não é de demonstração: pulado."))
            return None
        user = User.objects.create_user(
            username=username,
            password=senha,
            email=f"{username}@{DOMINIO_DEMO}",
            role=role,
            **extras,
        )
        ConsentLog.objects.create(user=user, terms_version=TermsVersion.current().version, user_agent="seed_demo")
        return user

    def criar_empresas(self, senha):
        empresas = {}
        for username, nome, aprovada in EMPRESAS:
            user = self.criar_conta(username, senha, User.Role.COMPANY)
            if user:
                empresas[username] = CompanyProfile.objects.create(user=user, company_name=nome, approved=aprovada)
        return empresas

    def criar_desafios(self, empresas, agora):
        desafios = []
        for dados in DESAFIOS:
            empresa = empresas.get(dados["empresa"])
            if not empresa:
                continue
            desafio = Challenge.objects.create(
                company=empresa,
                title=dados["titulo"],
                description=dados["descricao"],
                deadline=agora + timedelta(days=dados["prazo_em"]),
                difficulty=dados["dificuldade"],
                status=dados["status"],
            )
            # created_at é preenchido sozinho com "agora" (auto_now_add); o update grava a data retroativa
            desafio.created_at = agora - timedelta(days=dados["publicado_ha"])
            Challenge.objects.filter(pk=desafio.pk).update(created_at=desafio.created_at)
            desafio.slug_demo = dados["slug"]
            desafios.append(desafio)
        return desafios

    def criar_estudantes(self, senha):
        estudantes = []
        for nome_completo in ESTUDANTES:
            nome, sobrenome = nome_completo.split(" ", 1)
            user = self.criar_conta(
                gerar_username(nome_completo), senha, User.Role.STUDENT, first_name=nome, last_name=sobrenome
            )
            if user:
                # Perfil do portfólio; o último estudante da lista fica privado, para demonstrar a opção
                StudentProfile.objects.create(
                    user=user,
                    bio=APRESENTACOES[len(estudantes) % len(APRESENTACOES)],
                    github_username=user.username.replace(".", "-"),
                    portfolio_public=nome_completo != ESTUDANTES[-1],
                )
                estudantes.append(user)
        return estudantes

    def criar_raio_x(self, submissao, enviado_em):
        """Raio-X fictício da entrega: os repositórios de demonstração não existem no GitHub,
        então o relatório é montado aqui em vez de vir da análise real."""
        # Sorteio próprio, pela URL: não muda a sequência que define notas e entregas
        sorteio = random.Random(submissao.repo_url)
        linguagem, linguagens, tecnologias = sorteio.choice(PERFIS_RAIO_X)
        commits = sorteio.choice([1, 6, 9, 14, 21, 33])
        dias = min(commits, sorteio.randint(1, 6))
        snapshot = RepoSnapshot(
            submission=submissao,
            status=RepoSnapshot.Status.READY,
            commit_sha=hashlib.sha1(submissao.repo_url.encode()).hexdigest(),
            main_language=linguagem,
            report={
                "languages": [{"name": nome, "percent": percentual} for nome, percentual in linguagens],
                "main_language": linguagem,
                "files": sorteio.randint(8, 60),
                "lines": sorteio.randint(300, 4000),
                "readme": sorteio.choice(["ok", "ok", "ok", "minimo", "ausente"]),
                "test_files": sorteio.choice([0, 0, 2, 4, 7, 12]),
                "practices": sorteio.sample(PRATICAS_RAIO_X, k=sorteio.randint(1, 4)),
                "stack": tecnologias,
                "issues": sorteio.choice([[], [], [], [], ["env_file"]]),
                "history": {
                    "count": commits, "capped": False, "active_days": dias, "authors": 1,
                    "first_at": (enviado_em - timedelta(days=dias)).isoformat(),
                    "last_at": enviado_em.isoformat(),
                },
                "repo": {"fork": False, "parent": "", "created_at": ""},
            },
        )
        snapshot.alerts = build_alerts(snapshot)
        snapshot.save()
        # O commit é registrado no momento da entrega
        RepoSnapshot.objects.filter(pk=snapshot.pk).update(created_at=enviado_em)

    def criar_submissoes(self, estudantes, desafios, sorteio, agora):
        # Rascunho não recebe submissão
        abertos_ou_encerrados = [d for d in desafios if d.status != Challenge.Status.DRAFT]
        total_submissoes = 0
        total_avaliacoes = 0
        if not abertos_ou_encerrados:
            return total_submissoes, total_avaliacoes

        for posicao, aluno in enumerate(estudantes):
            # Quem vem antes na lista tende a ter notas maiores, para o ranking ficar variado
            nota_base = 93 - posicao * 1.7
            quantidade = min(sorteio.randint(2, 4), len(abertos_ou_encerrados))

            for desafio in sorteio.sample(abertos_ou_encerrados, k=quantidade):
                # A entrega acontece entre a publicação do desafio e o prazo (ou hoje, se o prazo é futuro)
                inicio = desafio.created_at + timedelta(days=1)
                fim = min(agora, desafio.deadline) - timedelta(hours=1)
                enviado_em = inicio + (fim - inicio) * sorteio.random()

                # O link de deploy é opcional: só parte das entregas informa
                tem_deploy = sorteio.random() < 0.4
                submissao = Submission.objects.create(
                    challenge=desafio,
                    student=aluno,
                    repo_url=f"https://github.com/{aluno.username}/{desafio.slug_demo}",
                    deploy_url=f"https://{desafio.slug_demo}-{aluno.username}.up.railway.app" if tem_deploy else "",
                    description=sorteio.choice(NOTAS_DO_ESTUDANTE),
                )
                Submission.objects.filter(pk=submissao.pk).update(submitted_at=enviado_em)
                self.criar_raio_x(submissao, enviado_em)
                total_submissoes += 1

                # A avaliação só começa depois do prazo ou do encerramento (RN41). Desafio encerrado
                # já foi todo avaliado; no que está com o prazo vencido, parte ainda aguarda a empresa
                encerrado = desafio.status == Challenge.Status.CLOSED
                if encerrado or (desafio.deadline_passed and sorteio.random() < 0.7):
                    nota = round(nota_base + sorteio.uniform(-12, 12))
                    avaliacao = Evaluation.objects.create(
                        submission=submissao,
                        evaluated_by=desafio.company.user,
                        score=max(0, min(100, nota)),
                        strengths=sorteio.choice(PONTOS_FORTES),
                        improvements=sorteio.choice(PONTOS_A_MELHORAR),
                    )
                    avaliado_em = min(agora, enviado_em + timedelta(days=sorteio.randint(1, 3)))
                    Evaluation.objects.filter(pk=avaliacao.pk).update(evaluated_at=avaliado_em)
                    total_avaliacoes += 1

        return total_submissoes, total_avaliacoes
