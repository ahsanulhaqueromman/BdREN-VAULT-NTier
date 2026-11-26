"""Tables of radius. Import from here: from apps.radius.models import RadCheck"""
from apps.radius.models.radius import (  # noqa: F401
    RadCheck,
    RadUserGroup,
    RadGroupReply,
    Nas,
    RadPostAuth,
    NO_DEVICE,
    ROLE_SUGGESTIONS,
    ROLE_MAX_LEN,
    clean_role,
    NasRole,
    UserGrant,
    UserDevice,
    AuditLog,
)
