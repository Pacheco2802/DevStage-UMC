from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def criar_perfis_privados(apps, schema_editor):
    """Quem já tinha conta aceitou termos em que o portfólio só aparecia para usuários
    autenticados. Por isso essas contas começam com o portfólio privado, e cada estudante
    decide se quer torná-lo público. Só as contas novas nascem com o portfólio público."""
    User = apps.get_model("accounts", "User")
    StudentProfile = apps.get_model("accounts", "StudentProfile")
    StudentProfile.objects.bulk_create(
        StudentProfile(user=user, portfolio_public=False)
        for user in User.objects.filter(role="STUDENT")
    )


class Migration(migrations.Migration):
    """Perfil do estudante (RF15): apresentação, usuário do GitHub e visibilidade do portfólio."""

    dependencies = [
        ('accounts', '0007_publica_termos_1_2'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bio', models.TextField(blank=True, max_length=500)),
                ('github_username', models.CharField(blank=True, max_length=39, validators=[django.core.validators.RegexValidator('^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$', 'Informe apenas o nome de usuário do GitHub, sem @ e sem o endereço completo.')])),
                ('portfolio_public', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='student_profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(criar_perfis_privados, migrations.RunPython.noop),
    ]
