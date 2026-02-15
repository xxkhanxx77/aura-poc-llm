from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings

security = HTTPBearer(auto_error=False)

# Default demo tenant -- used when no JWT is provided
DEMO_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")


class TenantContext(BaseModel):
    tenant_id: UUID
    user_id: str
    role: str


def get_tenant(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TenantContext:
    """Extract tenant context from JWT, or fall back to demo tenant.

    In production, remove the fallback and set auto_error=True.
    """
    if credentials is None:
        return TenantContext(
            tenant_id=DEMO_TENANT_ID,
            user_id="demo-user",
            role="admin",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return TenantContext(
            tenant_id=UUID(payload["tenant_id"]),
            user_id=payload["sub"],
            role=payload.get("role", "user"),
        )
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant credentials",
        ) from exc
