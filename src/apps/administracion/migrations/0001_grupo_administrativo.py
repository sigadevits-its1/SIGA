from django.db import migrations

GRUPO = "Administrativo"


def crear_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GRUPO)


def borrar_grupo(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GRUPO).delete()


class Migration(migrations.Migration):
    """Crea el rol del personal de secretaría y preceptoría."""

    dependencies = [("auth", "0012_alter_user_first_name_max_length")]

    operations = [migrations.RunPython(crear_grupo, borrar_grupo)]
