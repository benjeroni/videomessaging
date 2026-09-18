from django.db import migrations

def seed_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model('auth', 'User')
    coordinator, _ = Group.objects.get_or_create(name='Coordinator')
    Group.objects.get_or_create(name='Recorder')
    # Preserve existing campaign access for legacy staff accounts.
    for user in User.objects.filter(is_staff=True, is_superuser=False):
        user.groups.add(coordinator)

class Migration(migrations.Migration):
    dependencies = [('messaging', '0003_recipient_assigned_to')]
    operations = [migrations.RunPython(seed_roles, migrations.RunPython.noop)]
