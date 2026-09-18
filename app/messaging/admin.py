from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import Group, User
from .access import COORDINATOR, RECORDER, role_for

ROLE_CHOICES = [('recorder', 'Recorder'), ('coordinator', 'Coordinator'), ('admin', 'Admin')]

class RoleChangeForm(UserChangeForm):
    role = forms.ChoiceField(choices=ROLE_CHOICES, help_text='Admins manage accounts. Coordinators manage campaigns and assignments. Recorders only record assigned recipients.')
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['role'].initial = ('admin' if self.instance.is_superuser else 'coordinator' if self.instance.groups.filter(name=COORDINATOR).exists() else 'recorder')

class RoleCreationForm(AdminUserCreationForm):
    role = forms.ChoiceField(choices=ROLE_CHOICES, initial='recorder')

class WorkspaceUserAdmin(UserAdmin):
    form = RoleChangeForm
    add_form = RoleCreationForm
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal information', {'fields': ('first_name', 'last_name', 'email')}),
        ('Access', {'fields': ('is_active', 'role')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('username', 'role', 'usable_password', 'password1', 'password2')}),)
    list_display = ('username', 'email', 'workspace_role', 'is_active')
    list_filter = ('is_active', 'groups', 'is_superuser')
    filter_horizontal = ()
    @admin.display(description='Role')
    def workspace_role(self, obj):
        return (role_for(obj) or 'No access').title()
    def save_model(self, request, obj, form, change):
        role = form.cleaned_data['role']
        obj.is_superuser = role == 'admin'
        obj.is_staff = role == 'admin'
        super().save_model(request, obj, form, change)
        obj.groups.remove(*Group.objects.filter(name__in=[COORDINATOR, RECORDER]))
        if role != 'admin':
            group, _ = Group.objects.get_or_create(name=COORDINATOR if role == 'coordinator' else RECORDER)
            obj.groups.add(group)
        obj.user_permissions.clear()

admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, WorkspaceUserAdmin)
# Only admins can enter Django Admin, even if an old account has is_staff=True.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser
