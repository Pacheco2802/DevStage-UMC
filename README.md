# DevStage — Plataforma de conexão entre empresas e estudantes

Projeto Final de Curso — Engenharia de Software, Universidade de Mogi das Cruzes (UMC).

**Autor:** Pedro Henrique Prado Pacheco

**Sistema em produção:** https://devstage-umc.up.railway.app

---

## Sobre

Empresas publicam **desafios técnicos**; estudantes desenvolvem a solução e **submetem o repositório**; a empresa **avalia** a entrega com nota e feedback; as avaliações geram o **portfólio** de cada estudante e um **ranking** entre os estudantes.

```
Empresa publica desafio → Estudante submete solução → Empresa avalia → Portfólio e ranking
```

## Funcionalidades

| Perfil | Funcionalidades |
|---|---|
| **Visitante** | Cadastro como estudante ou empresa (com aceite dos Termos de Uso e da Política de Privacidade) · Login |
| **Estudante** | Listar desafios abertos · Ver detalhes · Submeter solução (URL do repositório GitHub, URL de deploy opcional e descrição) · Acompanhar as próprias submissões e avaliações · Portfólio com as avaliações recebidas |
| **Empresa** | Criar e editar desafios (rascunho, aberto ou encerrado, com prazo) · Listar os próprios desafios · Ver as submissões recebidas · Avaliar submissões (nota de 0 a 10 e feedback) |
| **Administrador** | Aprovar empresas (Django Admin) — empresa só publica desafios após aprovação · Gestão geral dos cadastros |
| **Todos (logados)** | Dashboard com indicadores e gráficos por perfil · Ranking e portfólios dos estudantes · Página **Meus Dados** (LGPD) |

### Regras de negócio implementadas (principais)

- Empresa só cria desafios depois de **aprovada** por um administrador.
- Desafio em **rascunho** só é visível para a empresa dona.
- Estudante só submete em desafio **aberto** e **dentro do prazo**, e **uma única vez** por desafio.
- Apenas o perfil **estudante** submete; apenas a **empresa dona** do desafio avalia as submissões dele.
- A URL do repositório é **validada na API do GitHub** (formato `https://github.com/usuario/repositorio` e existência do repositório).
- O ranking e o portfólio são calculados a partir das **avaliações** recebidas.

### Integração com API externa

- **GitHub REST API** (`integrations/github_client.py`): ao submeter uma solução, o sistema consulta `api.github.com/repos/{owner}/{repo}` para confirmar que o repositório existe. Timeout de 3 s; repositório inexistente (404) é recusado; se a API estiver indisponível (falha de rede, limite de requisições ou erro 5xx), aceita a URL com formato válido para não bloquear o estudante.
- **API JSON interna** (`/dashboard/api/dados/`, Django REST Framework): alimenta os gráficos do dashboard; exige usuário autenticado.

### LGPD

- Registro do **consentimento** no cadastro (versão dos termos aceita, data, IP e navegador) e possibilidade de **revogação**.
- Página **Meus Dados**: visualização, **exportação** dos dados pessoais em JSON e **exclusão da conta por anonimização**: remove nome, e-mail e acesso do titular, mas mantém desafios e submissões para não quebrar dados de outros usuários; desafios abertos de uma empresa excluída são encerrados.
- **Trilha de auditoria** (app `audit`): login, logout e criação/alteração/exclusão dos principais registros.
- Termos de Uso, Política de Privacidade e contato do encarregado (DPO) acessíveis no rodapé.

## Stack

| Camada | Tecnologia |
|---|---|
| Back-end | Python 3.12 · Django 5.2 · Django REST Framework |
| Front-end | Django Templates · HTMX · Alpine.js · Tailwind CSS (via CDN) |
| Banco de dados | PostgreSQL |
| Testes | pytest · pytest-django |
| Produção | Railway · gunicorn · WhiteNoise |

### Apps Django

| App | Responsabilidade |
|---|---|
| `accounts` | Usuário customizado (perfis estudante, empresa e admin), cadastro, perfil de empresa, consentimento e Meus Dados (LGPD) |
| `challenges` | Desafios, submissões e avaliações |
| `portfolio` | Portfólio do estudante e ranking |
| `dashboard` | Indicadores, gráficos e endpoint JSON |
| `integrations` | Cliente da API do GitHub |
| `audit` | Trilha de auditoria |
| `core` | Termos, privacidade, decorators de permissão e utilitários |

---

## Como acessar a versão em produção

1. Acesse https://devstage-umc.up.railway.app.
2. Crie uma conta pelo link de cadastro na tela de login (**estudante** ou **empresa**).
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

### Variáveis de ambiente

| Variável | Descrição | Exemplo (local) |
|---|---|---|
| `SECRET_KEY` | Chave secreta do Django | gere com `get_random_secret_key()` |
| `DEBUG` | Modo de depuração | `True` (local) · `False` (produção) |
| `ALLOWED_HOSTS` | Domínios aceitos, separados por vírgula | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | Origens aceitas em POST, com esquema | vazio (local) · `https://<domínio>` (produção) |
| `DATABASE_URL` | Conexão com o PostgreSQL | `postgres://user:senha@localhost:5432/devstage` |
| `CONN_MAX_AGE` | Segundos que cada conexão com o banco é reaproveitada (0 desliga) | `60` |
| `DJANGO_LOG_LEVEL` | Nível de log do Django (opcional) | `INFO` |

## Testes

```bash
python -m pytest
```

| Tipo | Pasta | O que cobre |
|---|---|---|
| Unitários | `tests/unit/` | Regras de submissão, formulário de submissão e cliente do GitHub (com a API simulada) |
| Integração | `tests/integration/` | Fluxos HTTP completos: contas, desafios, submissão, avaliação, painel da empresa, portfólio, dashboard e LGPD |

Resultado atual: **114 testes passando**.

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
| Workers | `WEB_CONCURRENCY=3` (fórmula do gunicorn: 2 × CPUs + 1) |

Decisões de produção:

- **gunicorn** como servidor WSGI (múltiplos processos; o `runserver` é só para desenvolvimento).
- **WhiteNoise** serve os arquivos estáticos com compressão e nomes com hash (cache de longa duração).
- **HTTPS atrás de proxy:** `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS` e cookies `Secure` quando `DEBUG=False`.
- **Conexões persistentes** com o banco (`CONN_MAX_AGE` + `CONN_HEALTH_CHECKS`).
- **Logs** de erro enviados ao console, capturados pelo Railway.
