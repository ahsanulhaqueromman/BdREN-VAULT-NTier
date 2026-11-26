"""`python manage.py syslog_receive`: the syslog receiver for Command History (see business/commandlog/syslog_receiver.py).

Production: started by systemd (deploy/systemd/vault-syslog.service), which gives it the right to use port 514
without running as root. Settings in .env: SYSLOG_HOST (default 0.0.0.0) and SYSLOG_PORT (default 514).
"""
import os
import signal

from django.core.management.base import BaseCommand, CommandError

from business.commandlog.syslog_receiver import Receiver


class Command(BaseCommand):
    help = "Receive syslog from the network devices and keep the commands users ran (Command History)."

    def add_arguments(self, parser):
        parser.add_argument("--host", default=os.environ.get("SYSLOG_HOST", "0.0.0.0"))
        parser.add_argument("--port", type=int, default=int(os.environ.get("SYSLOG_PORT", "514")))

    def handle(self, *args, **opts):
        stop = {"now": False}

        def ask_stop(*_):
            stop["now"] = True

        signal.signal(signal.SIGTERM, ask_stop)
        signal.signal(signal.SIGINT, ask_stop)
        receiver = Receiver(opts["host"], opts["port"], out=lambda msg: self.stdout.write(msg))
        try:
            receiver.bind()
        except PermissionError:
            raise CommandError(f"No permission to use UDP port {opts['port']}. Run it through the vault-syslog "
                               "service (it has the right to use port 514) or choose a port above 1023.")
        except OSError as exc:
            raise CommandError(f"Cannot listen on UDP {opts['host']}:{opts['port']}: {exc}. Is another syslog "
                               "server (rsyslog, syslog-ng) already using this port?  sudo ss -ulnp | grep ':514 '")
        receiver.run(lambda: stop["now"])
        self.stdout.write("syslog receiver stopped")
