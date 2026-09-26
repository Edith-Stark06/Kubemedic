"""
API authentication and roles.

WHY THIS EXISTS
---------------
The approval gate is the point of the product, and it is only as strong as the
answer to "who approved this?". Before this module the approver was a string the
client chose, and every route -- including the ones that ship a bad image for a
demo -- was open to anyone who could reach the port.

MODEL
-----
Bearer tokens, each bound to an identity and a role:

    KUBEMEDIC_API_TOKENS="alice:approver:<token>,bob:viewer:<token>"

    viewer     read incidents, tickets, cluster state, provider status
    approver   viewer, plus open incidents, review, revise, execute
    admin      approver, plus presenter tooling (demo, fault injection, engine switch)

When a token is presented the approver recorded in the audit trail is the
token's identity. The `approver` field in a request body is ignored.

MODES
-----
KUBEMEDIC_REQUIRE_AUTH=true   production. Every route except liveness needs a
                              valid token. With no tokens configured the API
                              refuses everything: it fails closed.
otherwise                     development. No token is needed, the caller is an
                              admin, and the API says so at /api/limits. The API
                              binds to 127.0.0.1 by default; do not expose this
                              mode.

Tokens are compared in constant time. They are read through agent/secrets.py,
never logged, and never returned by any endpoint.
"""
from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from agent.secrets import get_secrets

log = logging.getLogger("kubemedic.auth")

ROLES = ("viewer", "approver", "admin")
_RANK = {role: i for i, role in enumerate(ROLES)}


@dataclass(frozen=True)
class Principal:
    identity: str
    role: str

    def can(self, role: str) -> bool:
        return _RANK[self.role] >= _RANK[role]


DEV_PRINCIPAL = Principal(identity="anonymous-dev", role="admin")


def auth_required() -> bool:
    return (os.getenv("KUBEMEDIC_REQUIRE_AUTH") or "").strip().lower() in (
        "1", "true", "yes",
    )


def load_tokens() -> list[tuple[str, Principal]]:
    """
    Parse KUBEMEDIC_API_TOKENS. Malformed entries are skipped and reported,
    never half-accepted: a typo must not silently create a weaker credential.
    """
    raw = get_secrets().get("KUBEMEDIC_API_TOKENS") or ""
    tokens: list[tuple[str, Principal]] = []
    for entry in (e.strip() for e in raw.split(",") if e.strip()):
        parts = entry.split(":", 2)
        if len(parts) != 3 or not all(parts) or parts[1] not in ROLES:
            log.error("[AUTH] ignoring a malformed KUBEMEDIC_API_TOKENS entry")
            continue
        identity, role, token = parts
        tokens.append((token, Principal(identity=identity, role=role)))
    return tokens


def presenter_tools_enabled() -> bool:
    """
    Demo fault injection, the fixture cluster and the engine switch.

    On by default in development, off by default when auth is required: a
    production API must not carry a route that ships a bad image.
    """
    explicit = (os.getenv("KUBEMEDIC_ENABLE_PRESENTER_TOOLS") or "").strip().lower()
    if explicit:
        return explicit in ("1", "true", "yes")
    return not auth_required()


def describe() -> dict[str, object]:
    return {
        "auth_required": auth_required(),
        "tokens_configured": len(load_tokens()),
        "presenter_tools_enabled": presenter_tools_enabled(),
    }


def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    if not auth_required():
        return DEV_PRINCIPAL

    tokens = load_tokens()
    if not tokens:
        # Auth was demanded but nothing can satisfy it. Fail closed.
        raise HTTPException(
            503,
            detail={
                "error": "auth_misconfigured",
                "message": "KUBEMEDIC_REQUIRE_AUTH is set but no valid "
                           "KUBEMEDIC_API_TOKENS are configured.",
            },
        )

    scheme, _, presented = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not presented.strip():
        raise HTTPException(
            401,
            detail={"error": "authentication_required",
                    "message": "Send 'Authorization: Bearer <token>'."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    match: Principal | None = None
    for token, principal in tokens:
        # Compare against every token so timing does not reveal which matched.
        if hmac.compare_digest(token.encode(), presented.strip().encode()):
            match = principal
    if match is None:
        raise HTTPException(
            401,
            detail={"error": "invalid_token", "message": "The token was not recognised."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return match


def require_role(role: str):
    """A dependency that admits only principals of at least `role`."""
    if role not in _RANK:
        raise ValueError(f"unknown role {role!r}")

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.can(role):
            raise HTTPException(
                403,
                detail={
                    "error": "forbidden",
                    "message": f"This action needs the {role!r} role; "
                               f"you have {principal.role!r}.",
                },
            )
        return principal

    return dependency


def require_presenter_tools(
    principal: Principal = Depends(require_role("admin")),
) -> Principal:
    """Admin, and presenter tooling switched on. Otherwise the route does not exist."""
    if not presenter_tools_enabled():
        raise HTTPException(404, detail="Not found")
    return principal
