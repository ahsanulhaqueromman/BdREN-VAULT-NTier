from django.urls import path

from presentation.scheduling import views

urlpatterns = [path("api/settings", views.settings_view, name="api-settings")]
