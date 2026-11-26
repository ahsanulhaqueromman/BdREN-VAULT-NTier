from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"               # keeps the table names and migration history
    verbose_name = "Accounts (users, login, roles)"
