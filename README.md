# DevStage - Plataforma de conexão entre empresas e estudantes

Projeto Final de Curso - Engenharia de Software, Universidade de Mogi das Cruzes (UMC).

**Autor:** Pedro Henrique Prado Pacheco

**Sistema em produção:** https://devstage-umc.up.railway.app

---

## Sobre

Empresas publicam **desafios técnicos**; estudantes desenvolvem a solução e **submetem o repositório**; a empresa **avalia** a entrega com nota e feedback; a nota vira **pontos** conforme a dificuldade do desafio; e os pontos formam o **portfólio público** de cada estudante e um **ranking** entre os estudantes.

```
Empresa publica desafio → Estudante submete solução → Empresa avalia → Pontos → Portfólio e ranking
```

## Funcionalidades

| Perfil | Funcionalidades |
|---|---|
| **Visitante** | Cadastro como estudante ou empresa (com aceite dos Termos de Uso e da Política de Privacidade) · Login · **Ranking** (paginado, com busca) e **portfólios públicos**, sem precisar de conta |
| **Estudante** | Listar desafios abertos, com busca por título ou empresa, filtro de dificuldade e paginação · Ver detalhes · Submeter solução (URL do repositório GitHub, URL de deploy opcional e descrição) · Acompanhar as próprias submissões, com nota, pontos e feedback · **Meu perfil** (apresentação, usuário do GitHub e portfólio público ou privado) |
| **Empresa** | Criar desafios com nível de dificuldade e prazo · Editar, **publicar** e **encerrar** os próprios desafios · Ver as submissões recebidas, com o raio-X de cada entrega · Avaliar submissões (nota de 0 a 100, pontos fortes e pontos a melhorar) |
| **Administrador** | Aprovar empresas (Django Admin) — empresa só publica desafios após aprovação · Consultar a trilha de auditoria · Corrigir avaliações · Gestão geral dos cadastros |
| **Todos (logados)** | Dashboard com indicadores e gráficos por perfil · Página **Meus Dados** (LGPD) |

A página **Ajuda** (`/ajuda/`), pública e com link no menu e no rodapé de todas as telas, resume o passo a passo de cada perfil e traz o manual do sistema completo, em PDF. Para quem está autenticado, o link abre a ajuda já na parte do seu perfil.

### Regras de negócio implementadas (principais)

- Empresa só cria desafios depois de **aprovada** por um administrador.
- Todo desafio tem um **nível de dificuldade** (Iniciante, Intermediário ou Avançado) e um **prazo no futuro**.
- **Ciclo de vida do desafio:** Rascunho → Aberto → Encerrado, sem voltar e sem pular etapa. Um desafio encerrado não pode ser reaberto.
- Desafio em **rascunho** só é visível para a empresa dona.
- Depois da **primeira submissão**, o desafio não pode mais ser editado: as condições ficam iguais para todos os participantes.
- Estudante só submete em desafio **aberto** e **dentro do prazo**, e **uma única vez** por desafio (regra conferida na aplicação e garantida por restrição no banco).
- Apenas o perfil **estudante** submete; apenas a **empresa dona** do desafio avalia as submissões dele.
- A URL do repositório é **validada na API do GitHub** (formato `https://github.com/usuario/repositorio` e existência do repositório).
- A avaliação só é liberada **depois do prazo ou do encerramento** do desafio, para que todos sejam avaliados nas mesmas condições.
- A avaliação tem **nota de 0 a 100**, **pontos fortes** e **pontos a melhorar** (mínimo de 20 caracteres cada). Cada submissão recebe **uma única avaliação**, que a empresa **não pode alterar**; correções são feitas pelo administrador e ficam na auditoria.
- **Pontos = nota × peso da dificuldade** (Iniciante ×1, Intermediário ×2, Avançado ×3). O peso é gravado na avaliação, então os pontos não mudam se o desafio for alterado depois.
- O **ranking** é ordenado pelo total de pontos; o desempate é pela maior média de notas e, depois, pela ordem alfabética. É calculado por agregação no banco, sem tabela própria.
- As **listagens são paginadas**: ranking com 50 estudantes por página (a busca filtra sem alterar a posição no ranking geral), projetos com 12 e submissões recebidas com 20.
- **Limite de tentativas de login:** 5 falhas para o mesmo nome de usuário, ou 20 do mesmo IP, em 15 minutos bloqueiam novas tentativas até as falhas saírem dessa janela. Vale também para a área administrativa, e o início do bloqueio fica na auditoria.
- O **portfólio** é público por padrão, nunca mostra o e-mail nem o texto do feedback, e o estudante pode torná-lo **privado** (a página passa a responder 404 e ele sai do ranking).

### Integração com API externa

- **GitHub REST API** (`integrations/github_client.py`): ao submeter uma solução, o sistema consulta `api.github.com/repos/{owner}/{repo}` para confirmar que o repositório existe. Timeout de 3 s; repositório inexistente (404) é recusado; se a API estiver indisponível (falha de rede, limite de requisições ou erro 5xx), aceita a URL com formato válido para não bloquear o estudante.
- **Raio-X da entrega** (`integrations/repo_analysis.py`, `challenges/services.py`): no momento da entrega o sistema **registra o commit** que está no repositório, então o que for enviado depois não entra na avaliação. Quando a empresa abre a avaliação, o repositório é baixado nesse commit (uma única requisição, lida em memória) e a tela mostra linguagens, tecnologias, tamanho, histórico de commits, um checklist (README, testes, `.gitignore`, licença, Docker, CI, `.env` de exemplo) e **pontos de atenção** para conferência: `.env` ou chave privada versionados, dependências versionadas, fork, repositório mais antigo que o desafio, commit único, mais de um autor e o mesmo repositório entregue por outro estudante. O estudante vê o resumo da própria entrega e o portfólio exibe linguagem e tecnologias de cada projeto. Nomes e e-mails dos autores dos commits não são armazenados. Se o GitHub estiver indisponível, a entrega é aceita e o raio-X pode ser gerado depois.
- **API JSON interna** (`/dashboard/api/dados/`, Django REST Framework): alimenta os gráficos do dashboard; exige usuário autenticado.

### LGPD

- Registro do **consentimento** no cadastro (versão dos termos aceita, data, IP e navegador) e possibilidade de **revogação**.
- Página **Meus Dados** (direitos do art. 18): **acesso** aos dados, consentimentos e histórico de atividade; **correção** dos dados cadastrais; **portabilidade** com exportação em JSON (cadastro, perfil, consentimentos, submissões e avaliações recebidas ou realizadas); e **exclusão da conta por anonimização**, confirmada com a **senha**: remove nome, e-mail, dados do perfil e acesso do titular e tira o portfólio do ar, mas mantém desafios e submissões para não quebrar dados de outros usuários; desafios abertos de uma empresa excluída são encerrados.
- **Portfólio público com escolha do titular:** contas novas nascem com o portfólio público, informado nos termos; contas criadas antes da versão 1.2 dos termos começam com o portfólio **privado**, e só o estudante pode torná-lo público.
- **Trilha de auditoria** (app `audit`): login, logout e criação/alteração/exclusão dos principais registros, com **quem fez**, de qual IP e em qual tela; exportação de dados, revogação do consentimento e exclusão da conta também são registradas. Os registros são somente leitura.
- **Termos versionados**: cada versão publicada dos Termos de Uso e da Política de Privacidade fica registrada com data e resumo das mudanças, e as anteriores continuam disponíveis para consulta. Ao publicar uma versão nova, o usuário logado precisa dar **novo aceite** no acesso seguinte; enquanto não aceita, continua podendo ler os documentos, exportar seus dados, revogar o consentimento e excluir a conta.
- Termos de Uso, Política de Privacidade e contato do encarregado (DPO) acessíveis no rodapé.

## Stack

| Camada | Tecnologia |
|---|---|
| Back-end | Python 3.12 · Django 5.2 · Django REST Framework |
| Front-end | Django Templates · HTMX · Alpine.js · Tailwind CSS (via CDN) |
| Banco de dados | PostgreSQL |
| Testes | pytest · pytest-django · pytest-cov (coverage.py) |
| Produção | Railway · gunicorn · WhiteNoise |

### Apps Django

| App | Responsabilidade |
|---|---|
| `accounts` | Usuário customizado (perfis estudante, empresa e admin), cadastro, perfis de empresa e de estudante, consentimento, versões dos termos e Meus Dados (LGPD) |
| `challenges` | Desafios, submissões, avaliações com pontuação e raio-X da entrega |
| `portfolio` | Ranking, portfólio público e edição do perfil do estudante |
| `dashboard` | Indicadores, gráficos e endpoint JSON |
| `integrations` | Cliente da API do GitHub |
| `audit` | Trilha de auditoria (sinais e middleware que identifica o autor de cada alteração) |
| `core` | Termos, privacidade, página de ajuda, decorators de permissão e utilitários |

---

## Como acessar a versão em produção

1. Acesse https://devstage-umc.up.railway.app.
2. O ranking (`/portfolio/ranking/`) e os portfólios públicos podem ser vistos sem conta. Para o restante, crie uma conta pelo link de cadastro na tela de login (**estudante** ou **empresa**).
3. Contas de **empresa** precisam de aprovação de um administrador para publicar desafios. O acesso administrativo **não é publicado aqui**; para avaliação, solicite ao autor.

> Não há senhas, tokens ou dados pessoais reais neste repositório.

## Como executar localmente

**Pré-requisitos:** Python 3.12 e PostgreSQL em execução.

```bash
# 1. Clonar e entrar na pasta
git clone https://github.com/Pacheco2802/DevStage-UMC.git
cd DevStage-UMC

# 2. Criar e ativar o ambiente virtual
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 3. Instalar as dependências
python -m pip install -r requirements.txt

# 4. Configurar as variáveis de ambiente
copy .env.example .env          # Windows  (Linux/macOS: cp .env.example .env)
# edite o .env: SECRET_KEY e DATABASE_URL do seu Postgres local

# 5. Criar as tabelas e um administrador
python manage.py migrate
python manage.py createsuperuser

# 6. Subir o servidor de desenvolvimento
python manage.py runserver
```

Acesse http://localhost:8000.

### Dados de demonstração (opcional)

O comando `seed_demo` cria empresas, desafios (nas três dificuldades e nas três situações), estudantes com perfil, submissões com raio-X e avaliações fictícias para explorar o sistema sem cadastrar tudo à mão. A senha das contas criadas vem da variável de ambiente `SEED_DEMO_PASSWORD` (não fica no código).

```bash
set SEED_DEMO_PASSWORD=escolha-uma-senha     # Windows  (Linux/macOS: export SEED_DEMO_PASSWORD=...)
python manage.py seed_demo                   # cria os dados
python manage.py seed_demo --limpar          # remove só os dados de demonstração
```

As contas de demonstração usam e-mails do domínio reservado `demo.devstage.test`; é por essa marca que `--limpar` apaga apenas elas, sem tocar em contas reais. Rodar o comando duas vezes não duplica nada.

### Massa de dados em volume (opcional)

O comando `seed_volume` gera milhares de registros fictícios, para os testes de carga e para ver as listagens com volume. As contas usam o domínio `volume.devstage.test`, não têm senha utilizável e são removidas à parte, sem tocar nas de demonstração.

```bash
python manage.py seed_volume                 # 2.000 estudantes, 120 desafios, 10.000 submissões
python manage.py seed_volume --estudantes 500 --desafios 40 --submissoes 3000
python manage.py seed_volume --limpar        # remove só a massa de volume
```

### Variáveis de ambiente

| Variável | Descrição | Exemplo (local) |
|---|---|---|
| `SECRET_KEY` | Chave secreta do Django | gere com `get_random_secret_key()` |
| `DEBUG` | Modo de depuração | `True` (local) · `False` (produção) |
| `ALLOWED_HOSTS` | Domínios aceitos, separados por vírgula | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | Origens aceitas em POST, com esquema | vazio (local) · `https://<domínio>` (produção) |
| `DATABASE_URL` | Conexão com o PostgreSQL | `postgres://user:senha@localhost:5432/devstage` |
| `CONN_MAX_AGE` | Segundos que cada conexão com o banco é reaproveitada (0 desliga) | `60` |
| `GITHUB_TOKEN` | Token de leitura pública do GitHub (opcional): sobe o limite da API de 60 para 5.000 requisições por hora | vazio |
| `DJANGO_LOG_LEVEL` | Nível de log do Django (opcional) | `INFO` |
| `SECURE_HSTS_SECONDS` | Duração do HSTS em segundos (opcional) | `0` com `DEBUG=True` · 30 dias em produção |
| `DPO_NAME` / `DPO_EMAIL` | Nome e e-mail do encarregado de dados exibidos no rodapé e na política (opcionais) | — |

## Testes

```bash
python -m pytest                                        # todos os testes
python -m pytest tests/unit                             # só os unitários (não usam o banco)
python -m pytest --cov                                  # com o relatório de cobertura
```

| Tipo | Pasta | O que cobre |
|---|---|---|
| Unitários | `tests/unit/` | Classes e funções de regra de negócio, sem banco e sem rede: `Challenge` (peso, prazo, ciclo de vida, liberação da avaliação), `Evaluation` (cálculo dos pontos), formulários de desafio, de avaliação e de submissão, regras de submissão e de avaliação, decoradores de perfil, middlewares, cliente do GitHub (com a API simulada) e análise dos arquivos do repositório |
| Integração | `tests/integration/` | Fluxos HTTP completos, com o PostgreSQL de teste: contas, desafios e ciclo de vida, submissão, avaliação e pontuação, painel da empresa, ranking, portfólio e perfil, dashboard, LGPD, versionamento dos termos, auditoria, limite de tentativas de login, raio-X da entrega, migrações de dados, paginação, desempenho com 10.000 submissões e os comandos de dados de demonstração e de volume |

Resultado atual: **462 testes passando** (215 unitários e 247 de integração), com **99% de cobertura** do código da aplicação, medida pelo coverage.py. Só os testes unitários, que rodam sem banco em poucos segundos, cobrem 62%. O teste de desempenho usa uma base de 10.000 submissões. A meta do projeto é de no mínimo 50%; a configuração da medição está em `.coveragerc`.

### Teste de carga

O script `tests/load/carga.py` mede o sistema sob carga de duas formas: em **etapas**, com usuários virtuais navegando com pausas (estudantes autenticados e visitantes), e em **rajada**, com um total fixo de requisições disparadas sem pausa. Ele só faz leituras e login, então pode ser repetido sem sujar a base.

```bash
# rajada: 10.000 requisições nas páginas públicas, 100 conexões ao mesmo tempo
python tests/load/carga.py --base http://localhost:8000 --rajada 10000 --concorrencia 100 --processos 4

# etapas com usuários autenticados (a senha das contas vem de uma variável de ambiente)
set CARGA_SENHA=senha-das-contas-de-demonstracao     # Windows  (Linux/macOS: export CARGA_SENHA=...)
python tests/load/carga.py --base http://localhost:8000 --contas msato,cferraz,lprado --usuarios 25,50,100 --processos 4
```

**Em produção** (Railway, 3 workers do Gunicorn com 4 threads cada), com a massa de volume carregada (2.000 estudantes e 10.000 submissões a mais), nas páginas públicas:

| Medição | Requisições | Erros | Req./s | Mediana | p95 |
|---|---:|---:|---:|---:|---:|
| Rajada, 100 conexões | 10.000 | 0 | 123,3 | 613 ms | 1.070 ms |
| 50 visitantes navegando | 1.448 | 0 | 31,5 | 276 ms | 573 ms |
| 100 visitantes navegando | 2.875 | 0 | 62,5 | 283 ms | 518 ms |

Na rajada, o tempo dentro do servidor (medido pelos logs da borda do Railway) teve mediana de 312 ms; cerca de 215 ms de cada resposta são a viagem de rede até a região us-west2. Com 200 visitantes simultâneos, o servidor seguiu respondendo com mediana de 52 a 61 ms e sem erros, mas o gerador de carga observou esperas longas, que não foram explicadas.

**Em ambiente local** (3 processos, `DEBUG=False`, mesma massa de volume), com usuários autenticados, o sistema fica dentro de 2 s no percentil 95 até 100 usuários ativos ao mesmo tempo. O ponto fraco é o **login em massa**: o hash PBKDF2 da senha custa cerca de 0,5 s por login, de propósito. Com 160 logins em 20 segundos, os processos ficam ocupados só com logins; com 4 threads por processo o ritmo sobe de 26 para 71 requisições por segundo, e por isso a produção passou a usar threads (`GUNICORN_CMD_ARGS=--threads=4`). O limite de tentativas de login também ajuda: a tentativa bloqueada não chega a calcular o hash.

---

## Deploy (Railway)

O deploy é automático a cada push na branch **`main`** (fluxo: desenvolvimento na `develop` → merge na `main` → deploy).

| Etapa | Configuração no serviço do Railway |
|---|---|
| Build | `python manage.py collectstatic --noinput` |
| Pre-deploy | `python manage.py migrate --noinput` — roda antes de trocar a versão; se falhar, a versão anterior continua no ar |
| Start | `gunicorn config.wsgi --access-logfile -` |
| Healthcheck | `/accounts/login/` |
| Banco | PostgreSQL do próprio Railway, via `DATABASE_URL=${{Postgres.DATABASE_URL}}` (rede interna) |
| Workers | `WEB_CONCURRENCY=3` (fórmula do gunicorn: 2 × CPUs + 1) e `GUNICORN_CMD_ARGS=--threads=4` (4 threads por worker, definido depois do teste de carga) |

Decisões de produção:

- **gunicorn** como servidor WSGI (múltiplos processos; o `runserver` é só para desenvolvimento).
- **WhiteNoise** serve os arquivos estáticos com compressão e nomes com hash (cache de longa duração).
- **HTTPS atrás de proxy:** `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS` e cookies `Secure` quando `DEBUG=False`. O redirecionamento de HTTP para HTTPS é feito pelo proxy do Railway, e o Django envia o cabeçalho **HSTS**.
- **Conexões persistentes** com o banco (`CONN_MAX_AGE` + `CONN_HEALTH_CHECKS`).
- **Logs** de erro enviados ao console, capturados pelo Railway.
