"""The organization-wide brand colours (DBD "Colour palette", decision W4-12). No I/O here.

Admins set them from /admin/settings with a Material Theme Builder export, or one generated
from a seed colour. Only the parts the app uses are kept: the light and dark schemes and the
five tonal palettes. The frontend maps them onto the DBD tokens (src/app/theme/material.ts);
status colours never come from here.
"""

from __future__ import annotations

import re
from typing import Any

from mms_common.errors import ValidationFailed

# Every colour role of a Material 3 scheme, as Material Theme Builder names them.
ROLES: tuple[str, ...] = (
    "primary", "surfaceTint", "onPrimary", "primaryContainer", "onPrimaryContainer",
    "secondary", "onSecondary", "secondaryContainer", "onSecondaryContainer",
    "tertiary", "onTertiary", "tertiaryContainer", "onTertiaryContainer",
    "error", "onError", "errorContainer", "onErrorContainer",
    "background", "onBackground", "surface", "onSurface", "surfaceVariant", "onSurfaceVariant",
    "outline", "outlineVariant", "shadow", "scrim", "inverseSurface", "inverseOnSurface",
    "inversePrimary", "primaryFixed", "onPrimaryFixed", "primaryFixedDim",
    "onPrimaryFixedVariant", "secondaryFixed", "onSecondaryFixed", "secondaryFixedDim",
    "onSecondaryFixedVariant", "tertiaryFixed", "onTertiaryFixed", "tertiaryFixedDim",
    "onTertiaryFixedVariant", "surfaceDim", "surfaceBright", "surfaceContainerLowest",
    "surfaceContainerLow", "surfaceContainer", "surfaceContainerHigh", "surfaceContainerHighest",
)
SCHEMES: tuple[str, ...] = ("light", "dark")
PALETTES: tuple[str, ...] = ("primary", "secondary", "tertiary", "neutral", "neutral-variant")
TONES: tuple[str, ...] = (
    "0", "5", "10", "15", "20", "25", "30", "35", "40", "50", "60", "70", "80", "90", "95",
    "98", "99", "100",
)
NAME_MAX = 120

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _hex(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _HEX.match(value):
        raise ValidationFailed(f"{where} must be a colour like #0A6780", code="invalid_theme")
    return value.upper()


def _exactly(found: dict[str, Any], expected: tuple[str, ...], where: str) -> None:
    missing = [k for k in expected if k not in found]
    extra = sorted(k for k in found if k not in expected)
    if missing:
        raise ValidationFailed(f"{where} is missing {', '.join(missing)}", code="invalid_theme")
    if extra:
        raise ValidationFailed(f"{where} has unknown {', '.join(extra)}", code="invalid_theme")


def normalize(material: dict[str, Any]) -> dict[str, Any]:
    """Check a theme has exactly the expected roles and tones as #RRGGBB, and upper-case them.
    Raises ValidationFailed (422 `invalid_theme`) naming what is wrong."""
    schemes = material.get("schemes")
    palettes = material.get("palettes")
    if not isinstance(schemes, dict) or not isinstance(palettes, dict):
        raise ValidationFailed("A theme needs schemes and palettes", code="invalid_theme")
    _exactly(schemes, SCHEMES, "schemes")
    _exactly(palettes, PALETTES, "palettes")
    out_schemes: dict[str, dict[str, str]] = {}
    for scheme in SCHEMES:
        roles = schemes[scheme]
        if not isinstance(roles, dict):
            raise ValidationFailed(f"schemes.{scheme} must be an object", code="invalid_theme")
        _exactly(roles, ROLES, f"schemes.{scheme}")
        out_schemes[scheme] = {r: _hex(roles[r], f"schemes.{scheme}.{r}") for r in ROLES}
    out_palettes: dict[str, dict[str, str]] = {}
    for palette in PALETTES:
        tones = palettes[palette]
        if not isinstance(tones, dict):
            raise ValidationFailed(f"palettes.{palette} must be an object", code="invalid_theme")
        _exactly(tones, TONES, f"palettes.{palette}")
        out_palettes[palette] = {t: _hex(tones[t], f"palettes.{palette}.{t}") for t in TONES}
    name = material.get("name")
    if name is not None and (not isinstance(name, str) or len(name.strip()) > NAME_MAX):
        raise ValidationFailed(f"name must be text of at most {NAME_MAX} characters",
                               code="invalid_theme")
    if isinstance(name, str):
        name = name.strip() or None
    return {
        "name": name,
        "seed": _hex(material["seed"], "seed") if material.get("seed") is not None else None,
        "schemes": out_schemes,
        "palettes": out_palettes,
    }


def summary(material: dict[str, Any] | None) -> dict[str, Any]:
    """What the audit trail keeps of a theme: enough to see what changed, not every role."""
    if material is None:
        return {"custom": False, "name": None, "seed": None, "light_primary": None,
                "dark_primary": None}
    return {
        "custom": True,
        "name": material.get("name"),
        "seed": material.get("seed"),
        "light_primary": material["schemes"]["light"]["primary"],
        "dark_primary": material["schemes"]["dark"]["primary"],
    }
