from django.db import migrations
from django.utils import timezone

VERSION = "1.2"

# Um parágrafo por mudança (linha em branco entre eles): é o texto da tela de novo aceite
SUMMARY = """\
Termos, item 2: no momento da entrega, a plataforma registra o commit do repositório. A avaliação considera o código nesse commit; o que for enviado depois não é levado em conta.

Termos, item 2: a avaliação passa a ser feita depois do prazo ou do encerramento do desafio, com nota de 0 a 100, pontos fortes e pontos a melhorar, e não é alterada pela empresa. A nota vira pontos conforme a dificuldade do desafio, e o ranking é ordenado pelos pontos.

Política, item 4: o ranking e o portfólio passam a ser páginas públicas, visíveis também para quem não tem conta, sem o e-mail e sem o texto do feedback. Você pode tornar o portfólio privado em Meu perfil. Sua conta foi criada antes desta versão e, por isso, começa com o portfólio privado: ele só fica público se você escolher.

Política, item 1: passa a listar os dados do perfil do estudante (apresentação e usuário do GitHub, opcionais) e os dados do repositório da entrega (commit registrado, linguagens, tecnologias, tamanho, presença de README e de testes, contagens e datas dos commits). Nomes e e-mails dos autores dos commits não são armazenados.

Política, itens 3 e 4: a integração com o GitHub passa a servir também para registrar o commit e gerar o raio-X da entrega. A empresa do desafio vê o raio-X com pontos de atenção; o estudante vê o resumo da própria entrega; o portfólio exibe linguagem e tecnologias de cada projeto avaliado."""


def publish(apps, schema_editor):
    TermsVersion = apps.get_model("accounts", "TermsVersion")
    # A versão passa a valer no instante em que esta migração roda em cada ambiente
    TermsVersion.objects.create(version=VERSION, published_at=timezone.now(), summary=SUMMARY)


def unpublish(apps, schema_editor):
    apps.get_model("accounts", "TermsVersion").objects.filter(version=VERSION).delete()


class Migration(migrations.Migration):
    """Publica a versão 1.2, que acompanha o raio-X da entrega, a pontuação e o portfólio público.
    O texto está em core/templates/core/legal/1.2/."""

    dependencies = [
        ('accounts', '0006_publica_termos_1_1'),
    ]

    operations = [
        migrations.RunPython(publish, unpublish),
    ]
