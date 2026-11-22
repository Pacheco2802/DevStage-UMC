from django.db import migrations, models
import django.core.validators


def converter_avaliacoes(apps, schema_editor):
    """As avaliações existentes usavam nota de 0 a 10 e um campo único de feedback.
    A nota passa para a escala de 0 a 100 e o texto antigo vira os pontos fortes.
    Os desafios existentes ficam como Iniciante (peso 1), então pontos = nota."""
    Evaluation = apps.get_model("challenges", "Evaluation")
    for evaluation in Evaluation.objects.all():
        evaluation.score = evaluation.score * 10
        evaluation.strengths = evaluation.feedback
        evaluation.weight = 1
        evaluation.points = evaluation.score
        evaluation.save(update_fields=["score", "strengths", "weight", "points"])


def desfazer_conversao(apps, schema_editor):
    Evaluation = apps.get_model("challenges", "Evaluation")
    for evaluation in Evaluation.objects.all():
        evaluation.score = evaluation.score // 10
        evaluation.feedback = "\n\n".join(
            text for text in [evaluation.strengths, evaluation.improvements] if text
        )
        evaluation.save(update_fields=["score", "feedback"])


class Migration(migrations.Migration):
    """Dificuldade do desafio (RN20) e avaliação com nota de 0 a 100, feedback em duas
    partes e pontos calculados pelo peso da dificuldade (RN42, RN43, RN45)."""

    dependencies = [
        ('challenges', '0004_reposnapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='challenge',
            name='difficulty',
            field=models.CharField(choices=[('BEGINNER', 'Iniciante'), ('INTERMEDIATE', 'Intermediário'), ('ADVANCED', 'Avançado')], default='BEGINNER', max_length=12),
        ),
        # A restrição antiga (0 a 10) sai antes da conversão das notas, e a nova entra depois
        migrations.RemoveConstraint(
            model_name='evaluation',
            name='evaluation_score_between_0_and_10',
        ),
        migrations.AlterField(
            model_name='evaluation',
            name='score',
            field=models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)]),
        ),
        migrations.AddField(
            model_name='evaluation',
            name='strengths',
            field=models.TextField(default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='evaluation',
            name='improvements',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='evaluation',
            name='weight',
            field=models.PositiveSmallIntegerField(default=1, editable=False),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='evaluation',
            name='points',
            field=models.PositiveSmallIntegerField(default=0, editable=False),
            preserve_default=False,
        ),
        migrations.RunPython(converter_avaliacoes, desfazer_conversao),
        migrations.RemoveField(
            model_name='evaluation',
            name='feedback',
        ),
        migrations.AddConstraint(
            model_name='evaluation',
            constraint=models.CheckConstraint(condition=models.Q(('score__gte', 0), ('score__lte', 100)), name='evaluation_score_between_0_and_100'),
        ),
    ]
