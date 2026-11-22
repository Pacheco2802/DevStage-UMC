"""Gera uma massa de dados fictícios em volume, para testes de carga e de desempenho.

Uso:
    python manage.py seed_volume                                   # 2.000 estudantes, 120 desafios, 10.000 submissões
    python manage.py seed_volume --estudantes 500 --submissoes 3000
    python manage.py seed_volume --limpar                          # remove só a massa de volume

É separado do seed_demo de propósito. As contas daqui usam o domínio reservado DOMINIO_VOLUME,
então podem ser removidas sem tocar nas contas de demonstração nem nas reais. Elas não têm
senha utilizável: servem para dar volume às listagens, não para entrar no sistema.
"""
import hashlib
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.signals import post_delete
from django.utils import timezone

from accounts.models import CompanyProfile, StudentProfile
from audit.signals import _log_delete
from challenges.models import Challenge, Evaluation, RepoSnapshot, Submission

User = get_user_model()

DOMINIO_VOLUME = "volume.devstage.test"
LOTE = 1000

NOMES = [
    "Ana", "Bruno", "Carla", "Daniel", "Eduarda", "Fábio", "Gabriela", "Heitor", "Isadora", "João", "Karina", "Leonardo",
    "Mariana", "Nicolas", "Olívia", "Paulo", "Rafaela", "Samuel", "Tatiane", "Ulisses", "Valentina", "William", "Yasmin",
    "Arthur", "Beatriz", "Caio", "Débora", "Enzo", "Fernanda", "Guilherme", "Helena", "Igor", "Juliana", "Kevin", "Lívia",
    "Matheus", "Natália", "Otávio", "Priscila", "Rodrigo",
]
SOBRENOMES = [
    "Almeida", "Barbosa", "Cardoso", "Dias", "Esteves", "Ferreira", "Gomes", "Henriques", "Ibrahim", "Jesus", "Klein", "Lima",
    "Machado", "Nascimento", "Oliveira", "Pereira", "Queiroz", "Ribeiro", "Souza", "Teixeira", "Uchoa", "Vieira", "Xavier",
    "Araújo", "Batista", "Castro", "Domingues", "Farias", "Guimarães", "Lopes", "Martins", "Novaes", "Pinto", "Rezende",
    "Santos", "Tavares", "Vasconcelos", "Zanetti", "Moraes", "Correia",
]
EMPRESAS = [
    "Aurora Dados", "Bússola Tech", "Cobalto Sistemas", "Delta Logística", "Estuário Labs", "Farol Pagamentos", "Granito Cloud",
    "Horizonte Saúde", "Ípsilon Educação", "Jangada Software", "Kairós Energia", "Litoral Digital", "Mirante Analytics",
    "Nascente Agro", "Órbita Seguros", "Planalto Varejo", "Quilha Marítima", "Ribeira Fintech", "Serrano Mobilidade", "Trilho Games",
]
TEMAS = [
    "API de agendamento", "Painel de indicadores", "Importador de planilhas", "Encurtador de links", "Catálogo de produtos",
    "Sistema de reservas", "Controle de estoque", "Fila de atendimento", "Conversor de moedas", "Gerador de relatórios",
    "Monitor de sensores", "Aplicativo de tarefas", "Busca de endereços", "Carteira digital", "Portal de vagas",
]
CONTEXTOS = [
    "para clínicas", "para pequenas lojas", "para transportadoras", "para escolas", "para condomínios", "para restaurantes",
    "para academias", "para cooperativas",
]
PERFIS_DE_CODIGO = [
    ["Python", ["Django", "pytest"]], ["Python", ["FastAPI", "PostgreSQL"]], ["JavaScript", ["Node.js", "Express"]],
    ["TypeScript", ["Next.js", "React"]], ["Java", ["Spring Boot"]], ["C#", [".NET"]], ["Go", []], ["PHP", ["Laravel"]],
]


class Command(BaseCommand):
    help = "Gera dados fictícios em volume (milhares de registros) para testes de carga."

    def add_arguments(self, parser):
        parser.add_argument("--estudantes", type=int, default=2000)
        parser.add_argument("--desafios", type=int, default=120)
        parser.add_argument("--submissoes", type=int, default=10000)
        parser.add_argument("--limpar", action="store_true", help="Remove a massa de volume criada por este comando.")

    def handle(self, *args, **options):
        if options["limpar"]:
            self.limpar()
            return
        if self.contas().exists():
            self.stdout.write(self.style.WARNING("A massa de volume já existe. Rode com --limpar antes de criar de novo."))
            return

        estudantes, desafios, submissoes = options["estudantes"], options["desafios"], options["submissoes"]
        if min(estudantes, desafios, submissoes) < 1:
            raise CommandError("Estudantes, desafios e submissões precisam ser maiores que zero.")
        # Cada estudante entrega no máximo uma vez por desafio em que cabe entrega (os rascunhos ficam de fora)
        if submissoes > estudantes * desafios * 0.8:
            raise CommandError("Submissões demais para essa quantidade de estudantes e desafios.")

        with transaction.atomic():
            resumo = self.criar(estudantes, desafios, submissoes)
        self.stdout.write(self.style.SUCCESS(
            "Massa de volume criada: {empresas} empresas, {desafios} desafios, {estudantes} estudantes, "
            "{submissoes} submissões e {avaliacoes} avaliações.".format(**resumo)
        ))

    # ---------- consulta e limpeza ----------

    def contas(self):
        return User.objects.filter(email__endswith="@" + DOMINIO_VOLUME)

    def limpar(self):
        total = self.contas().count()
        # A exclusão em cascata apagaria dezenas de milhares de linhas e gravaria um registro de
        # auditoria para cada uma. Isto é limpeza de dados de teste, não ação de usuário, então
        # os sinais de exclusão ficam desligados só durante a remoção.
        modelos = [User, CompanyProfile, StudentProfile, Challenge, Submission, Evaluation]
        for modelo in modelos:
            post_delete.disconnect(_log_delete, sender=modelo)
        try:
            self.contas().delete()
        finally:
            for modelo in modelos:
                post_delete.connect(_log_delete, sender=modelo)
        self.stdout.write(self.style.SUCCESS(f"{total} contas da massa de volume removidas, com tudo que dependia delas."))

    # ---------- criação ----------

    def criar(self, total_estudantes, total_desafios, total_submissoes):
        # bulk_create grava em lotes e não dispara os sinais de auditoria: são dados de teste
        sorteio = random.Random(2311)
        agora = timezone.now()
        sem_senha = make_password(None)  # senha inutilizável: ninguém entra com estas contas

        empresas = self.criar_empresas(sem_senha)
        desafios = self.criar_desafios(empresas, total_desafios, sorteio, agora)
        estudantes = self.criar_estudantes(total_estudantes, sorteio, sem_senha)
        submissoes = self.criar_submissoes(estudantes, desafios, total_submissoes, sorteio, agora)
        avaliacoes = self.criar_avaliacoes(submissoes, sorteio, agora)
        self.criar_raio_x(submissoes, sorteio)
        return {
            "empresas": len(empresas), "desafios": len(desafios), "estudantes": len(estudantes),
            "submissoes": len(submissoes), "avaliacoes": avaliacoes,
        }

    def criar_empresas(self, sem_senha):
        usuarios = User.objects.bulk_create([
            User(username=f"empresa.volume{numero:02d}", email=f"empresa{numero:02d}@{DOMINIO_VOLUME}",
                 role=User.Role.COMPANY, password=sem_senha)
            for numero in range(1, len(EMPRESAS) + 1)
        ])
        return CompanyProfile.objects.bulk_create([
            CompanyProfile(user=usuario, company_name=nome, approved=True) for usuario, nome in zip(usuarios, EMPRESAS)
        ])

    def criar_desafios(self, empresas, total, sorteio, agora):
        desafios = []
        for numero in range(total):
            # 6 em cada 10 já encerrados (com avaliações), 3 abertos e 1 aberto com o prazo vencido
            faixa = numero % 10
            if faixa < 6:
                status, prazo = Challenge.Status.CLOSED, agora - timedelta(days=sorteio.randint(3, 60))
            elif faixa < 9:
                status, prazo = Challenge.Status.OPEN, agora + timedelta(days=sorteio.randint(5, 45))
            else:
                status, prazo = Challenge.Status.OPEN, agora - timedelta(days=sorteio.randint(1, 5))
            desafios.append(Challenge(
                company=empresas[numero % len(empresas)],
                title=f"{sorteio.choice(TEMAS)} {sorteio.choice(CONTEXTOS)} #{numero + 1}",
                description=(
                    "Desafio fictício da massa de volume. Construa a solução com testes automatizados das regras "
                    "principais e explique no README as decisões de arquitetura e como executar o projeto."
                ),
                deadline=prazo, status=status, difficulty=list(Challenge.Difficulty)[numero % 3],
            ))
        desafios = Challenge.objects.bulk_create(desafios, batch_size=LOTE)
        # created_at recebe "agora" sozinho (auto_now_add); a atualização em lote grava a data retroativa
        for desafio in desafios:
            desafio.created_at = min(desafio.deadline, agora) - timedelta(days=sorteio.randint(20, 40))
        Challenge.objects.bulk_update(desafios, ["created_at"], batch_size=LOTE)
        return desafios

    def criar_estudantes(self, total, sorteio, sem_senha):
        usuarios = []
        for numero in range(1, total + 1):
            nome, sobrenome = sorteio.choice(NOMES), sorteio.choice(SOBRENOMES)
            usuarios.append(User(
                username=f"aluno.volume{numero:05d}", first_name=nome, last_name=sobrenome,
                email=f"aluno{numero:05d}@{DOMINIO_VOLUME}", role=User.Role.STUDENT, password=sem_senha,
            ))
        usuarios = User.objects.bulk_create(usuarios, batch_size=LOTE)
        StudentProfile.objects.bulk_create([StudentProfile(user=usuario) for usuario in usuarios], batch_size=LOTE)
        return usuarios

    def criar_submissoes(self, estudantes, desafios, total, sorteio, agora):
        pares = set()
        submissoes = []
        while len(submissoes) < total:
            estudante, desafio = sorteio.choice(estudantes), sorteio.choice(desafios)
            if (estudante.pk, desafio.pk) in pares:
                continue  # uma entrega por estudante em cada desafio, como exige a regra do sistema
            pares.add((estudante.pk, desafio.pk))
            submissoes.append(Submission(
                challenge=desafio, student=estudante,
                repo_url=f"https://github.com/{estudante.username.replace('.', '-')}/desafio-{desafio.pk}",
                description="Solução fictícia da massa de volume, com as decisões explicadas no README.",
            ))
        submissoes = Submission.objects.bulk_create(submissoes, batch_size=LOTE)
        # A entrega acontece entre a publicação do desafio e o prazo (ou agora, se o prazo é futuro)
        for submissao in submissoes:
            inicio = submissao.challenge.created_at
            fim = min(agora, submissao.challenge.deadline)
            submissao.submitted_at = inicio + (fim - inicio) * sorteio.random()
        Submission.objects.bulk_update(submissoes, ["submitted_at"], batch_size=LOTE)
        return submissoes

    def criar_avaliacoes(self, submissoes, sorteio, agora):
        avaliacoes = []
        for submissao in submissoes:
            desafio = submissao.challenge
            # RN41: só há avaliação em desafio encerrado ou com o prazo vencido; uma parte fica pendente
            if not desafio.accepts_evaluation or sorteio.random() > 0.9:
                continue
            nota = max(0, min(100, round(sorteio.gauss(72, 15))))
            avaliacoes.append(Evaluation(
                submission=submissao, evaluated_by=desafio.company.user, score=nota,
                strengths="Código organizado e regras principais cobertas por testes.",
                improvements="Vale documentar melhor os casos de erro e as decisões no README.",
                # bulk_create não passa pelo save(), então peso e pontos são calculados aqui
                weight=desafio.weight, points=nota * desafio.weight,
            ))
        Evaluation.objects.bulk_create(avaliacoes, batch_size=LOTE)
        return len(avaliacoes)

    def criar_raio_x(self, submissoes, sorteio):
        snapshots = []
        for submissao in submissoes:
            linguagem, tecnologias = sorteio.choice(PERFIS_DE_CODIGO)
            snapshots.append(RepoSnapshot(
                submission=submissao, status=RepoSnapshot.Status.READY, main_language=linguagem,
                commit_sha=hashlib.sha1(submissao.repo_url.encode()).hexdigest(),
                report={
                    "main_language": linguagem, "languages": [{"name": linguagem, "percent": 100}], "stack": tecnologias,
                    "files": sorteio.randint(8, 60), "lines": sorteio.randint(300, 4000), "readme": "ok",
                    "test_files": sorteio.choice([0, 2, 5, 9]), "practices": ["gitignore"], "issues": [],
                    "history": {"count": sorteio.randint(3, 40), "capped": False, "active_days": 3, "authors": 1},
                    "repo": {"fork": False, "parent": "", "created_at": ""},
                },
            ))
        RepoSnapshot.objects.bulk_create(snapshots, batch_size=LOTE)
