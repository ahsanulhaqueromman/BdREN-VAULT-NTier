"""Errors the application tier raises; the presentation tier turns them into JSON answers."""


class ApiError(Exception):
    """An error the browser should see as {"error": message} with an HTTP status."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message
