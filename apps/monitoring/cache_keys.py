"""Monitoring - cache keys shared by the ping monitor (services.py) and the Dashboard numbers (selectors.py)."""
LATEST_KEY = "ping-latest"  # last full-inventory ping result {device id: {up, ms}}, written by the monitor
FAILS_KEY = "ping-fails"    # consecutive failed sweeps per device id (offline only after 2 in a row)
