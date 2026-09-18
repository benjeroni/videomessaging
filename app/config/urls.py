from django.contrib import admin
from django.contrib.auth import views as auth
from django.http import HttpResponse
from django.urls import path
from messaging import views as v
urlpatterns = [
    path('health/', lambda request: HttpResponse('ok')),
    path('admin/', admin.site.urls),
    path('login/', auth.LoginView.as_view(), name='login'),
    path('logout/', auth.LogoutView.as_view(), name='logout'),
    path('', v.dashboard, name='dashboard'),
    path('campaign/new/', v.campaign_form, name='campaign_new'),
    path('campaign/<int:pk>/', v.campaign_detail, name='campaign'),
    path('campaign/<int:pk>/settings/', v.campaign_form, name='campaign_settings'),
    path('campaign/<int:pk>/delete/', v.campaign_delete, name='campaign_delete'),
    path('campaign/<int:pk>/recipients/', v.recipients, name='recipients'),
    path('campaign/<int:pk>/assign/', v.assign_recipients, name='assign_recipients'),
    path('campaign/<int:pk>/import/', v.import_csv, name='import'),
    path('template.csv', v.csv_template, name='csv_template'),
    path('recipient/<int:pk>/edit/', v.recipient_edit, name='recipient_edit'),
    path('recipient/<int:pk>/delete/', v.recipient_delete, name='recipient_delete'),
    path('recipient/<int:pk>/upload/', v.upload, name='upload'),
    path('campaign/<int:pk>/script/', v.save_script, name='save_script'),
    path('campaign/<int:pk>/record/', v.record, name='record'),
    path('campaign/<int:pk>/distribution/', v.distribution, name='distribution'),
    path('campaign/<int:pk>/analytics/', v.analytics, name='analytics'),
    path('v/<str:token>', v.public, name='public'),
    path('v/<str:token>/video', v.media, name='media'),
    path('api/event', v.event, name='event'),
]
