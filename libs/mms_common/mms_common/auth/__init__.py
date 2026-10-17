"""Authentication and authorization every service shares (TRD §6)."""

from mms_common.auth.deps import (
    Authenticator,
    actor_for,
    client_ip,
    current_user,
    install_auth,
    require_roles,
    require_service,
    require_staff,
)
from mms_common.auth.principal import ServicePrincipal, User
from mms_common.auth.roles import (
    ADMIN,
    CLIENT,
    STAFF,
    STAFF_WRITE,
    TECHNICIAN,
    USER_ROLES,
    VIEWER,
    valid_role_set,
)
from mms_common.auth.scope import scoped

__all__ = [
    "ADMIN",
    "CLIENT",
    "STAFF",
    "STAFF_WRITE",
    "TECHNICIAN",
    "USER_ROLES",
    "VIEWER",
    "Authenticator",
    "ServicePrincipal",
    "User",
    "actor_for",
    "client_ip",
    "current_user",
    "install_auth",
    "require_roles",
    "require_service",
    "require_staff",
    "scoped",
    "valid_role_set",
]
