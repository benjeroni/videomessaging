import os
from .access import role_for
def branding(request):
    role = role_for(request.user)
    return {'workspace_role': role, 'can_manage': role in ('admin', 'coordinator'), 'is_admin': role == 'admin', 'organization': os.getenv('ORGANIZATION_NAME', 'Video Messaging'), 'brand_logo': os.getenv('BRAND_LOGO_URL', ''), 'brand_heading': os.getenv('BRAND_HEADING', 'A message for you'), 'brand_footer': os.getenv('BRAND_FOOTER', 'Contact the team who sent you this message.')}
