"""Tables of commandlog. Import from here: from apps.commandlog.models import CommandEvent"""
from apps.commandlog.models.command_log import (  # noqa: F401
    CommandEvent,
    SyslogSource,
    ReceiverState,
)
