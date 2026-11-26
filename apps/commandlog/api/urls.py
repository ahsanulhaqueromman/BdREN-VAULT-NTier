from django.urls import path

from apps.commandlog.api import views

urlpatterns = [
    path("api/radius/commands", views.commands, name="api-radius-commands"),
    path("api/radius/commands/sessions", views.sessions, name="api-radius-command-sessions"),
    path("api/radius/commands/notes/<slug:note>/dismiss", views.dismiss_note, name="api-radius-command-dismiss"),
]
