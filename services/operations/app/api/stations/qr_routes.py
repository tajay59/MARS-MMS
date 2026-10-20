"""Station QR codes (TRD §3.2; PRD QR-1 to QR-4, QR-7).

The label holds an opaque token, not station data. Resolving it is an ordinary scoped read:
a client scanning another organization's station gets 404, exactly as for any other record
(rule 4, QR-4).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from mms_common.auth import User, require_roles
from mms_common.errors import AppError, NotFound
from mms_common.ids import UUID7_PATTERN
from pymongo.asynchronous.client_session import AsyncClientSession

from app.api.context import CtxDep
from app.api.stations import views
from app.api.stations.schemas import QrResolved, StationDetail
from app.domain.stations import stations as rules
from app.repo.stations import qr
from app.repo.stations import stations as repo

router = APIRouter(prefix="/api/v1/qr", tags=["qr"])
station_router = APIRouter(prefix="/api/v1/stations", tags=["qr"])

Reader = Annotated[User, Depends(require_roles())]
Admin = Annotated[User, Depends(require_roles("admin"))]
IdPath = Annotated[str, Path(pattern=UUID7_PATTERN)]
TokenPath = Annotated[str, Path(min_length=1, max_length=64)]


class CodeRevoked(AppError):
    status, code, title = 410, "qr_revoked", "This code is no longer valid"


@router.get("/{token}")
async def resolve(token: TokenPath, viewer: Reader, ctx: CtxDep) -> QrResolved:
    """QR-2, QR-3. A revoked code answers 410 to anyone who may see its station, and 404 to
    everyone else, so a client learns nothing about another organization's stations."""
    station = await repo.by_qr_token(ctx.db, token, viewer)
    if station is None:
        revoked_for = await qr.revoked_station(ctx.db, token)
        if revoked_for is not None and await repo.get(ctx.db, revoked_for, viewer) is not None:
            raise CodeRevoked()
        raise NotFound()
    return QrResolved(
        station_id=station["_id"], code=station["code"], name=station["name"],
        view="client" if viewer.is_client else "staff",
    )


@station_router.post("/{id}/qr/regenerate")
async def regenerate(id: IdPath, admin: Admin, ctx: CtxDep) -> StationDetail:
    """QR-7. Gives the station a new token and revokes the old one, in one transaction."""
    now = ctx.clock.now()
    emitter = ctx.emitter(admin)

    async def save(s: AsyncClientSession) -> dict[str, object]:
        current = await repo.require(ctx.db, id, session=s)
        await qr.revoke(
            ctx.db, current["qr_token"], station_id=id, now=now, by=admin.id, session=s
        )
        updated = await repo.update(
            ctx.db, id, {"qr_token": rules.new_qr_token()}, now=now, by=admin.id,
            expected_version=None, session=s,
        )
        await emitter.qr_regenerated(updated, s)
        return updated

    updated = await ctx.tx(save)
    installed = await views.installed_units(ctx, id, admin)
    due = min((u.calibration_due_at for u in installed if u.calibration_due_at), default=None)
    return StationDetail.build(updated, admin, installed, due)
