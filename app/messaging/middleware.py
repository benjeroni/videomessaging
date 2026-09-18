import logging
class PrivacyHeaders:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        response['Cache-Control'] = 'private, no-store'
        response['X-Robots-Tag'] = 'noindex, nofollow'
        response['Permissions-Policy'] = 'camera=(self), microphone=(self)'
        if response.status_code >= 500:
            logging.getLogger('operations').error('application_error status=%s', response.status_code)
        return response
