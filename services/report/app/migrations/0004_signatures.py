"""Signatures, and the hash of the content a signature stands for (TRD 5.4, 11.3; W17-3).

`signatures` is indexed by report version for the editor, with a unique index on a valid
signature per person per version (so two taps on Sign make one). Drafts made before W17 have
their facts but no `content_hash`: it is computed here, once, so the first signature can be bound
to something. `pdf_sha256` is what a public verify looks up (W17-12); only final and superseded
reports have one.
"""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.domain import content


async def up(db: AsyncDatabase[dict[str, Any]]) -> None:
    await db["signatures"].create_index([("report_id", 1), ("report_version", 1), ("valid", 1)])
    await db["signatures"].create_index(
        [("report_id", 1), ("report_version", 1), ("signer_id", 1)], unique=True,
        partialFilterExpression={"valid": True}, name="one_valid_signature_each",
    )
    await db["reports"].create_index(
        [("pdf_sha256", 1)], partialFilterExpression={"pdf_sha256": {"$type": "string"}},
        name="pdf_sha256",
    )
    pending = db["reports"].find(
        {"content_hash": None, "content.facts": {"$ne": None},
         "content.narrative": {"$ne": None}})
    async for doc in pending:
        await db["reports"].update_one(
            {"_id": doc["_id"], "content_hash": None},
            {"$set": {"content_hash": content.content_hash(doc["content"])}},
        )
