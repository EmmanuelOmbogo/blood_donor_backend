from django.urls import path
from . import views

urlpatterns = [
    path('auth/login', views.auth_login, name='auth_login'),
    path('auth/me', views.auth_me, name='auth_me'),
    path('dashboard/summary', views.dashboard_summary, name='dashboard_summary'),
    path('donors', views.donors_list_or_create, name='donors'),
    path('requests', views.requests_list_or_create, name='requests'),
    path('requests/<str:req_id>/alerts', views.request_dispatch_alerts, name='request_dispatch_alerts'),
    path('requests/<str:req_id>/status', views.request_update_status, name='request_update_status'),
    path('drives', views.drives_list, name='drives'),
    path('reports/summary', views.reports_summary, name='reports_summary'),
    path('sms/test', views.sms_test_send, name='sms_test_send'),
    path('sms/incoming', views.sms_incoming_webhook, name='sms_incoming_webhook'),
]
