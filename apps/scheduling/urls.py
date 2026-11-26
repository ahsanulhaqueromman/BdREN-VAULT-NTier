from django.urls import path

from apps.scheduling import views

urlpatterns = [path("api/settings", views.settings_view, name="api-settings")]
