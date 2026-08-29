"""
Derive this instance's public Journiv Plus capability.

Used by ``GET /instance/config`` so the frontend can gate Plus-only surfaces
(tag analytics, publishing, …) without probing a protected endpoint and
interpreting 403/503. The result carries capability flags only — see
:class:`app.schemas.instance.PlusCapability`.

Enforcement still lives on the protected endpoints themselves
(:func:`app.api.dependencies.get_plus_factory` + tier checks); this is a hint
for the UI, computed locally with no network call.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from importlib import import_module
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.core.config import JOURNIV_PLUS_DOC_URL
from app.core.logging_config import LogCategory
from app.models.instance_detail import InstanceDetail
from app.schemas.instance import PlusCapability

logger = logging.getLogger(LogCategory.PLUS)

# Paid tiers. "member" is the unlicensed / free state.
SUPPORTER_TIERS = frozenset({"supporter", "believer"})
DEFAULT_TIER = "member"


def _decode_claim_unverified(signed_license_b64: str) -> Optional[Dict[str, Any]]:
    """
    Read the license claim payload WITHOUT checking its signature.

    Only used when the compiled Plus module (which owns real verification) is
    not importable in this process — i.e. proxy mode, where the sidecar is the
    authority. Good enough for a UI hint; never for enforcement.
    """
    try:
        envelope = json.loads(base64.b64decode(signed_license_b64, validate=True))
        payload = json.loads(base64.b64decode(envelope["payload"], validate=True))
        return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 - any malformed input is simply "no claim"
        return None


def _claim_is_current(claim: Dict[str, Any]) -> bool:
    """True when neither the signed-license nor the subscription window has passed."""
    now = datetime.now(timezone.utc)
    for key in ("signed_license_expires_at", "subscription_expires_at"):
        raw = claim.get(key)
        if not raw:
            continue
        try:
            expires = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            return False
    return True


def _resolve_tier(signed_license_b64: str, install_id: str) -> str:
    """Resolve the tier from a stored signed license, verifying it when possible."""
    try:
        security = import_module("app.plus.core.security")
    except (ModuleNotFoundError, ImportError):
        security = None

    if security is not None:
        try:
            claim: Optional[Dict[str, Any]] = security.verify_license_signature(
                signed_license_base64=signed_license_b64,
                install_id=install_id,
            )
        except Exception as exc:  # noqa: BLE001 - expired / tampered / not configured
            logger.debug("Plus capability: license not usable (%s)", exc)
            return DEFAULT_TIER
    else:
        # Proxy mode: the .so is not in this image. Fall back to an unverified
        # read; the sidecar enforces the real thing on the analytics call.
        claim = _decode_claim_unverified(signed_license_b64)
        if claim is None or not _claim_is_current(claim):
            return DEFAULT_TIER

    tier = claim.get("tier") if isinstance(claim, dict) else None
    return tier if tier in SUPPORTER_TIERS else DEFAULT_TIER


def get_plus_capability(session: Session) -> PlusCapability:
    """Build the :class:`PlusCapability` block for the public instance config."""
    from app.plus import PLUS_AVAILABLE  # local import: avoids a startup cycle

    tier = DEFAULT_TIER
    instance = session.exec(select(InstanceDetail)).first()
    if instance is not None and instance.signed_license:
        tier = _resolve_tier(instance.signed_license, str(instance.install_id))

    return PlusCapability(
        available=bool(PLUS_AVAILABLE),
        tier=tier,
        upgrade_url=JOURNIV_PLUS_DOC_URL,
    )
