from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import auth


def test_clerk_session_membership_and_admin(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        auth,
        "settings",
        lambda: SimpleNamespace(
            clerk_jwks_url="https://clerk.example/jwks",
            clerk_issuer="https://clerk.example",
            clerk_organization_id="org_one",
        ),
    )
    monkeypatch.setattr(
        auth.jwt,
        "PyJWKClient",
        lambda url: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key())
        ),
    )

    def token(org_id, role, not_before_seconds=0):
        return jwt.encode(
            {
                "sub": "user_one",
                "iss": "https://clerk.example",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "nbf": datetime.now(timezone.utc) + timedelta(seconds=not_before_seconds),
                "o": {"id": org_id, "rol": role},
            },
            private_key,
            algorithm="RS256",
        )

    principal = auth.get_principal(f"Bearer {token('org_one', 'admin')}")
    assert principal.user_id == "user_one" and principal.is_admin
    assert auth.get_principal(f"Bearer {token('org_one', 'admin', 20)}").is_admin
    with pytest.raises(HTTPException) as too_early:
        auth.get_principal(f"Bearer {token('org_one', 'admin', 120)}")
    assert too_early.value.status_code == 401
    with pytest.raises(HTTPException) as denied:
        auth.get_principal(f"Bearer {token('org_two', 'admin')}")
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as invalid:
        auth.get_principal("Bearer not-a-token")
    assert invalid.value.status_code == 401
