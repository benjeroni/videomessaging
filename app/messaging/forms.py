from django import forms
from .models import Campaign, Recipient
class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ['name', 'description', 'script_text', 'status', 'landing_page_heading', 'landing_page_message', 'cta_text', 'cta_url']
    def clean_cta_url(self):
        url = self.cleaned_data['cta_url']
        if not url.startswith(('https://', 'http://')):
            raise forms.ValidationError('Use an HTTP or HTTPS URL.')
        return url

class RecipientForm(forms.ModelForm):
    class Meta:
        model = Recipient
        fields = ['external_id', 'first_name', 'last_name', 'email', 'phone', 'program', 'notes']
