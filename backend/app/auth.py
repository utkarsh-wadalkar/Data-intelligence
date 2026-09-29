import logging
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException

from .config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    user_id: str
    org_id: str
    is_admin: bool


def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    config = settings()
    if not config.clerk_jwks_url or not config.clerk_issuer or not config.clerk_organization_id:
        raise HTTPException(503, "Clerk authentication is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    token = authorization.removeprefix("Bearer ")
    try:
        key = jwt.PyJWKClient(config.clerk_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            issuer=config.clerk_issuer,
            leeway=60,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("Clerk session verification failed: %s", type(exc).__name__)
        raise HTTPException(401, "Invalid Clerk session") from exc
    # Clerk's active organization claims are signed into its session JWT.
    org_id = claims.get("org_id") or claims.get("o", {}).get("id")
    role = claims.get("org_role") or claims.get("o", {}).get("rol", "")
    if org_id != config.clerk_organization_id:
        raise HTTPException(403, "Active membership in this organization is required")
    return Principal(str(claims["sub"]), org_id, role in {"org:admin", "admin"})


PrincipalDep = Depends(get_principal)


def require_owner(principal: Principal, creator_id: str) -> None:
    if principal.user_id != creator_id and not principal.is_admin:
        raise HTTPException(403, "Only the creator or organization admin may manage this workflow")
