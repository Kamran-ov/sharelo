from django.db import migrations


def clear_stub_profiles(apps, schema_editor):
    # The stub Profile (email only) was never created by any code path; the next migration
    # adds a non-null `user`, so any row would have no valid owner.
    apps.get_model("accounts", "Profile").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(clear_stub_profiles, migrations.RunPython.noop)]
