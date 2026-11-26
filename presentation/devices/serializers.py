"""Devices - serializers: turn a Device into the JSON the browser receives.

Passwords never leave the server: they are replaced by yes/no flags (has_password, has_secret).
Input checks for a new or edited device are in services.clean_payload().
"""
from core.utils import fmt_dt


def device_json(device):
    """One device as sent to the browser."""
    return {"id": device.id, "name": device.name, "ip": device.ip, "device_type": device.device_type,
            "port": device.port, "username": device.username, "command": device.command,
            "last_status": device.last_status, "last_run": fmt_dt(device.last_run),
            "has_password": bool(device.password), "has_secret": bool(device.secret),
            "schedule_override": device.schedule_override, "schedule_days": device.schedule_days,
            "schedule_time": device.schedule_time, "created_at": fmt_dt(device.created_at),
            "created_by": device.created_by.username if device.created_by_id else "Legacy / unknown"}
