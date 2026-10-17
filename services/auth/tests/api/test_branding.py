"""Organization-wide brand colours (decision W4-12; DBD "Colour palette")."""

from typing import Any

import pytest

from app.domain import branding as rules


def theme(primary: str = "#0a6780", **extra: Any) -> dict[str, Any]:
    """A complete theme: every role and tone, primary set to `primary`."""
    scheme = {role: "#112233" for role in rules.ROLES}
    return {
        "name": "  Test theme  ",
        "seed": "#026d88",
        "schemes": {"light": {**scheme, "primary": primary}, "dark": dict(scheme)},
        "palettes": {p: {t: "#445566" for t in rules.TONES} for p in rules.PALETTES},
        **extra,
    }


async def test_built_in_colours_until_an_admin_saves(auth):
    r = await auth.http.get("/api/v1/auth/branding")
    assert r.status_code == 200
    assert r.json() == {"material": None, "version": 0, "updated_at": None}
    assert r.headers["Cache-Control"] == "no-store"


async def test_admin_saves_and_everyone_reads_them(auth):
    r = await auth.http.put("/api/v1/auth/branding", json={"material": theme(), "version": 0},
                            headers=auth.bearer("admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 1
    # Normalized: upper-case hex, trimmed name
    assert body["material"]["schemes"]["light"]["primary"] == "#0A6780"
    assert body["material"]["name"] == "Test theme"

    public = await auth.http.get("/api/v1/auth/branding")
    assert public.json() == body

    [event] = await auth.outbox("branding.updated")
    assert (event.key, event.aggregate_version, event.org_id) == ("branding", 1, None)
    assert (event.resource.type, event.resource.id) == ("settings", "branding")
    assert event.data == {"custom": True, "name": "Test theme", "seed": "#026D88"}
    assert event.audit == {
        "before": None,
        "after": {"custom": True, "name": "Test theme", "seed": "#026D88",
                  "light_primary": "#0A6780", "dark_primary": "#112233"},
    }


async def test_back_to_the_built_in_colours(auth):
    await auth.http.put("/api/v1/auth/branding", json={"material": theme(), "version": 0},
                        headers=auth.bearer("admin"))
    r = await auth.http.put("/api/v1/auth/branding", json={"material": None, "version": 1},
                            headers=auth.bearer("admin"))
    assert (r.status_code, r.json()["material"], r.json()["version"]) == (200, None, 2)
    events = await auth.outbox("branding.updated")
    assert events[-1].data == {"custom": False, "name": None, "seed": None}
    assert events[-1].audit["before"]["light_primary"] == "#0A6780"
    assert events[-1].audit["after"]["custom"] is False


async def test_a_stale_version_is_a_conflict(auth):
    first = await auth.http.put("/api/v1/auth/branding", json={"material": theme(), "version": 0},
                                headers=auth.bearer("admin"))
    assert first.status_code == 200
    for version in (0, 5):
        r = await auth.http.put("/api/v1/auth/branding",
                                json={"material": theme("#000000"), "version": version},
                                headers=auth.bearer("admin"))
        assert (r.status_code, r.json()["code"]) == (409, "version_conflict"), version
    assert len(await auth.outbox("branding.updated")) == 1


@pytest.mark.req("NFR-6")
@pytest.mark.parametrize(
    "change",
    [
        lambda t: t["schemes"]["light"].pop("onSurface"),
        lambda t: t["schemes"]["dark"].update(primaryDim="#000000"),
        lambda t: t["palettes"]["neutral"].pop("98"),
        lambda t: t["schemes"]["light"].update(primary="red"),
        lambda t: t["schemes"]["light"].update(primary="#0A6780; background:url(x)"),
        lambda t: t["palettes"].pop("tertiary"),
        lambda t: t.update(extendedColors=[]),
    ],
)
async def test_an_incomplete_or_unsafe_theme_is_refused(auth, change):
    """Only #RRGGBB values reach the CSS variables, and every role the app maps is there."""
    body = theme()
    change(body)
    r = await auth.http.put("/api/v1/auth/branding", json={"material": body, "version": 0},
                            headers=auth.bearer("admin"))
    assert r.status_code == 422, r.text
    assert (await auth.http.get("/api/v1/auth/branding")).json()["version"] == 0


def test_normalize_names_what_is_missing():
    body = theme()
    del body["schemes"]["light"]["outline"]
    with pytest.raises(Exception, match="schemes.light is missing outline"):
        rules.normalize(body)


def test_summary_of_the_built_in_colours():
    assert rules.summary(None)["custom"] is False
