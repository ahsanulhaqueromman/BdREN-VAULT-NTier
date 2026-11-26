from django.urls import path

from apps.monitoring.api import views

urlpatterns = [
    path("api/ping", views.ping_all, name="api-ping"),
    path("api/dashboard", views.dashboard, name="api-dashboard"),
    path("api/dashboard/ssh", views.dashboard_ssh, name="api-dashboard-ssh"),
]
