from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    roles: frozenset[str]

    def can_read_originals(self) -> bool:
        return bool(self.roles & {"admin", "reviewer", "data_protection_officer"})


async def get_principal(
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> Principal:
    # Dev headers make the API usable locally. Production must replace this dependency
    # with an OIDC/JWT verifier and reject missing credentials.
    try:
        user_id = UUID(x_user_id or "00000000-0000-0000-0000-000000000001")
        tenant_id = UUID(x_tenant_id or "00000000-0000-0000-0000-000000000001")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid identity"
        ) from exc
    roles = frozenset(
        item.strip() for item in (x_roles or "admin,reviewer").split(",") if item.strip()
    )
    return Principal(user_id=user_id, tenant_id=tenant_id, roles=roles)


def require_original_access(principal: Principal) -> Principal:
    if not principal.can_read_originals():
        raise HTTPException(status_code=403, detail="Original data access is not permitted")
    return principal
