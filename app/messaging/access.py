from functools import wraps
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from .models import Recipient

COORDINATOR = 'Coordinator'
RECORDER = 'Recorder'

def role_for(user):
    if not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return 'admin'
    groups = set(user.groups.values_list('name', flat=True))
    if COORDINATOR in groups:
        return 'coordinator'
    if RECORDER in groups:
        return 'recorder'
    return None

def can_manage(user):
    return role_for(user) in ('admin', 'coordinator')

def roles_required(*allowed):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if role_for(request.user) not in allowed:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator

workspace_user = roles_required('admin', 'coordinator', 'recorder')
manager = roles_required('admin', 'coordinator')

def recordable_recipients(user):
    rows = Recipient.objects.all()
    if can_manage(user):
        return rows
    if role_for(user) == 'recorder':
        return rows.filter(assigned_to=user)
    return rows.none()

def available_recorders():
    return User.objects.filter(is_active=True, is_superuser=False, groups__name=RECORDER).exclude(groups__name=COORDINATOR).distinct().order_by('username')
