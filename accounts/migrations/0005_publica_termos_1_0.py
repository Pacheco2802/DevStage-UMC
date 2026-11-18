from datetime import datetime, timezone

from django.db import migrations

VERSION = "1.0"


def publish(apps, schema_editor):
    TermsVersion = apps.get_model("accounts", "TermsVersion")
    TermsVersion.objects.create(
        version=VERSION,
        # 31/10/2026, meia-noite em Brasília: a data que já constava nos documentos
        published_at=datetime(2026, 10, 31, 3, 0, tzinfo=timezone.utc),
        summary="Primeira versão dos Termos de Uso e da Política de Privacidade.",
    )


def unpublish(apps, schema_editor):
    apps.get_model("accounts", "TermsVersion").objects.filter(version=VERSION).delete()


class Migration(migrations.Migration):
    """Registra a versão 1.0, que é a aceita por todas as contas criadas até aqui.
    O texto está em core/templates/core/legal/1.0/."""

    dependencies = [
        ('accounts', '0004_termsversion'),
    ]

    operations = [
        migrations.RunPython(publish, unpublish),
    ]
