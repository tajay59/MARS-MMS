"""The organization-wide brand colours (decision W4-12; DBD "Colour palette").

`GET` is public: the login page and the offline field shell use the colours too, and they hold
nothing private. The PWA keeps the last answer on the device, so the colours survive offline
(the service worker never caches it, TRD §13.3). Only an admin changes them, audited as
`branding.updated`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from mms_common.auth import User, require_roles
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import CtxDep
from app.api.schemas import BrandingIn, BrandingOut
from app.domain import branding as rules
from app.events.publish import ev
from app.repo import settings as settings_repo

router = APIRouter(prefix="/api/v1/auth/branding", tags=["branding"])

Admin = Annotated[User, Depends(require_roles("admin"))]


@router.get("")
async def get_branding(ctx: CtxDep) -> BrandingOut:
    return BrandingOut.of(await settings_repo.get_branding(ctx.db))


@router.put("")
async def put_branding(body: BrandingIn, admin: Admin, ctx: CtxDep) -> BrandingOut:
    material = (
        rules.normalize(body.material.model_dump(mode="json")) if body.material else None
    )
    current = await settings_repo.get_branding(ctx.db)
    before = current.get("material") if current else None
    now = ctx.clock.now()
    emitter = ctx.emitter(admin)

    async def save(s: AsyncClientSession) -> dict[str, Any]:
        doc = await settings_repo.save_branding(
            ctx.db, material, now=now, by=admin.id, expected_version=body.version, session=s
        )
        await emitter.emit(
            ev.BrandingUpdated(
                custom=material is not None,
                name=material["name"] if material else None,
                seed=material["seed"] if material else None,
            ),
            type_="branding.updated",
            key=settings_repo.BRANDING,
            resource=("settings", settings_repo.BRANDING),
            aggregate_version=doc["version"],
            org_id=None,
            session=s,
            before=rules.summary(before) if current else None,
            after=rules.summary(material),
        )
        return doc

    return BrandingOut.of(await ctx.tx(save))
