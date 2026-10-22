"""Configuration versions made from the visit board (W11-24, W11-37).

A version made by hand on the Configurations tab keeps W6's rule: each file belongs to one
version (CFG-2). A version made from a board's Config element repeats the files that did not
change, so the unique index now covers hand-made versions only (`from_board: false`). Existing
versions are all hand-made.
"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    versions = db["config_versions"]
    await versions.update_many({"from_board": {"$exists": False}}, {"$set": {"from_board": False}})
    try:
        await versions.drop_index("files.media_id_1")
    except OperationFailure:
        pass  # never made on this database
    await versions.create_index(
        [("files.media_id", ASCENDING)], unique=True, name="files_media_id_hand_made",
        partialFilterExpression={"from_board": False},
    )
    await versions.create_index("element_id", sparse=True)
