from django.db import migrations
from django.utils import timezone

VERSION = "1.1"

# Um parágrafo por mudança (linha em branco entre eles): é o texto da tela de novo aceite
SUMMARY = """\
Termos, item 7: mudanças nos termos deixam de ser avisadas por e-mail. A versão nova é apresentada no acesso seguinte à publicação e só vale depois de um novo aceite.

Política, item 1: passa a listar os dados guardados como prova do aceite (versão, data, IP e navegador) e as avaliações recebidas.

Política, item 4: informa que nome, notas e feedbacks das submissões avaliadas aparecem no ranking e no portfólio para os demais usuários autenticados.

Política, itens 2 e 7: indica a lei e o prazo de referência para a guarda dos registros de auditoria.

Política, item 9: explica como novas versões são publicadas e aceitas."""


def publish(apps, schema_editor):
    TermsVersion = apps.get_model("accounts", "TermsVersion")
    # A versão passa a valer no instante em que esta migração roda em cada ambiente
    TermsVersion.objects.create(version=VERSION, published_at=timezone.now(), summary=SUMMARY)


def unpublish(apps, schema_editor):
    apps.get_model("accounts", "TermsVersion").objects.filter(version=VERSION).delete()


class Migration(migrations.Migration):
    """Publica a versão 1.1. O texto está em core/templates/core/legal/1.1/.

    Modelo para as próximas versões: um commit com os dois templates da versão e uma
    migração como esta. Ao rodar, todos os usuários passam a ver a tela de novo aceite."""

    dependencies = [
        ('accounts', '0005_publica_termos_1_0'),
    ]

    operations = [
        migrations.RunPython(publish, unpublish),
    ]
