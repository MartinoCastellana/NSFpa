from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.db.session import get_session


async def session_dep(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    return session


async def principal_dep(principal: Principal = Depends(get_principal)) -> Principal:
    return principal


def reject_if_not_tenant(resource_tenant_id, principal: Principal) -> None:
    if resource_tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail="Resource not found")
