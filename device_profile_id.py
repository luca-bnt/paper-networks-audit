"""Strict device profile identifier for fingerprint graph matching.

DeviceProfileId groups papers that share the same browser hardware fingerprint
*and* display profile. It is stricter than legacy DeviceId (canvas + WebGL +
hardware + browser family only).

Formula (v1):
  SHA-256(
    CanvasHash | WebglHash | HwIdHash | UaFamilyHash
    | Platform | {ScreenWidth}x{ScreenHeight} | DevicePixelRatio
  )

Computed offline in the pipeline; the frontend only sees the digest as the
device hub id (hub prefix ``device:{DeviceProfileId}``).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

PROFILE_ID_RE = re.compile(r"^[a-f0-9]{64}$")

REQUIRED_V1_FIELDS = (
    "CanvasHash",
    "WebglHash",
    "HwIdHash",
    "UaFamilyHash",
    "Platform",
    "ScreenWidth",
    "ScreenHeight",
    "DevicePixelRatio",
)


def normalize_dpr(value: Any) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value).strip()


def normalize_screen(value: Any) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value).strip()


def _is_blank(value: Any) -> bool:
    if value is None or (isinstance(value, float) and value != value):
        return True
    return not str(value).strip()


def device_profile_key(row: Mapping[str, Any]) -> str:
    """Canonical pipe-separated key before hashing."""
    width = normalize_screen(row.get("ScreenWidth"))
    height = normalize_screen(row.get("ScreenHeight"))
    screen = f"{width}x{height}" if width and height else ""

    parts = [
        str(row.get("CanvasHash") or "").strip(),
        str(row.get("WebglHash") or "").strip(),
        str(row.get("HwIdHash") or "").strip(),
        str(row.get("UaFamilyHash") or "").strip(),
        str(row.get("Platform") or "").strip(),
        screen,
        normalize_dpr(row.get("DevicePixelRatio")),
    ]
    return "|".join(parts)


def validate_profile_row(row: Mapping[str, Any], *, strict: bool = True) -> list[str]:
    """Return validation errors for a fingerprint row (empty list = OK)."""
    errors: list[str] = []
    aid = row.get("ArticleId", "?")

    if strict:
        for field in REQUIRED_V1_FIELDS:
            if _is_blank(row.get(field)):
                errors.append(f"missing required field {field}")

    key = device_profile_key(row)
    if not any(part for part in key.split("|")):
        errors.append("empty profile key — no fingerprint components present")

    if not errors and strict:
        pid = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if not PROFILE_ID_RE.fullmatch(pid):
            errors.append(f"computed digest failed format check for ArticleId {aid}")

    return errors


def compute_device_profile_id(row: Mapping[str, Any], *, digest: bool = True, strict: bool = False) -> str:
    key = device_profile_key(row)
    row_errors = validate_profile_row(row, strict=strict)
    if row_errors:
        if strict:
            raise ValueError(f"ArticleId {row.get('ArticleId')}: {'; '.join(row_errors)}")
        if not any(part for part in key.split("|")):
            return str(row.get("DeviceId") or "").strip()

    if not digest:
        return key
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
