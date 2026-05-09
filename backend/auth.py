from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


@dataclass
class AuthUser:
    user_id: str
    email: str | None = None
    name: str | None = None


AUTH_SCHEME = HTTPBearer(auto_error=False)


def _auth_disabled() -> bool:
    raw = (os.getenv("OPENPOMELLI_DISABLE_AUTH") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _clerk_issuer() -> str:
    issuer = (os.getenv("CLERK_ISSUER") or "https://allowed-falcon-23.clerk.accounts.dev").strip()
    if issuer.endswith("/"):
        issuer = issuer[:-1]
    return issuer


def _clerk_jwks_url() -> str:
    env_url = (os.getenv("CLERK_JWKS_URL") or "").strip()
    if env_url:
        return env_url
    return f"{_clerk_issuer()}/.well-known/jwks.json"


@lru_cache(maxsize=1)
def _jwk_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(_clerk_jwks_url())


def _decode_clerk_token(token: str) -> dict:
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        audience = (os.getenv("CLERK_AUDIENCE") or "").strip()
        kwargs = {
            "algorithms": ["RS256"],
            "issuer": _clerk_issuer(),
            "options": {"require": ["sub", "iss"]},
        }
        if audience:
            kwargs["audience"] = audience
        else:
            kwargs["options"] = {**kwargs["options"], "verify_aud": False}
        payload = jwt.decode(token, signing_key.key, **kwargs)
        if not isinstance(payload, dict):
            raise HTTPException(status_code=401, detail="Invalid auth token payload")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid auth token: {exc.__class__.__name__}") from exc


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(AUTH_SCHEME)) -> AuthUser:
    if _auth_disabled():
        dev_user_id = (os.getenv("OPENPOMELLI_DEV_USER_ID") or "dev-user").strip() or "dev-user"
        dev_email = (os.getenv("OPENPOMELLI_DEV_USER_EMAIL") or "dev@openpomelli.local").strip() or None
        dev_name = (os.getenv("OPENPOMELLI_DEV_USER_NAME") or "Open Pomelli Dev").strip() or None
        return AuthUser(user_id=dev_user_id, email=dev_email, name=dev_name)

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = _decode_clerk_token(credentials.credentials)
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    email = payload.get("email")
    if not isinstance(email, str):
        email = None

    name = payload.get("name")
    if not isinstance(name, str):
        name = None

    return AuthUser(user_id=user_id, email=email, name=name)
