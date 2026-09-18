import logging
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Video
log = logging.getLogger('operations')

@receiver(post_delete, sender=Video)
def delete_video_file(sender, instance, **kwargs):
    if instance.stored_filename:
        path = settings.VIDEO_ROOT / instance.stored_filename
        transaction.on_commit(lambda: path.unlink(missing_ok=True))

@receiver(user_logged_in)
def login_log(sender, user, **kwargs):
    log.info('user_login user_id=%s', user.pk)
