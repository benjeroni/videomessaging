import secrets
from django.conf import settings
from django.db import models
from django.urls import reverse

def public_token():
    return secrets.token_urlsafe(24)

class Campaign(models.Model):
    STATUS = [(x, x.title()) for x in ('draft', 'recording', 'ready', 'archived')]
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    script_text = models.TextField(blank=True, max_length=20000)
    status = models.CharField(max_length=12, choices=STATUS, default='draft')
    cta_text = models.CharField(max_length=100, default='Learn More')
    cta_url = models.URLField()
    landing_page_heading = models.CharField(max_length=200, blank=True)
    landing_page_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name

class Recipient(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='recipients')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_recipients')
    external_id = models.CharField(max_length=100, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    program = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True, max_length=2000)
    public_token = models.CharField(max_length=64, unique=True, default=public_token, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['id']
    @property
    def public_url(self):
        return settings.BASE_URL + reverse('public', args=[self.public_token])
    def __str__(self):
        return f'{self.first_name} {self.last_name}'.strip()

class Video(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    recipient = models.OneToOneField(Recipient, on_delete=models.CASCADE, related_name='video')
    original_filename = models.CharField(max_length=255, blank=True)
    stored_filename = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=12, choices=[(x, x.title()) for x in ('uploaded', 'processing', 'ready', 'failed')], default='uploaded')
    duration_seconds = models.FloatField(default=0)
    recorded_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class AnalyticsEvent(models.Model):
    TYPES = [(x, x.replace('_', ' ').title()) for x in ('page_view', 'video_play', 'video_25', 'video_50', 'video_75', 'video_complete', 'cta_click')]
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    recipient = models.ForeignKey(Recipient, on_delete=models.CASCADE, related_name='events')
    video = models.ForeignKey(Video, on_delete=models.SET_NULL, null=True)
    event_type = models.CharField(max_length=20, choices=TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    session_id = models.UUIDField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['recipient', 'event_type', 'session_id'], name='unique_session_event')]
