"""`python -m app.cli` (STN-8): the import and seed an operator runs in the container."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from pymongo import AsyncMongoClient

from app import cli
from tests.conftest import seed_orgs

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_import_is_a_dry_run_until_commit_then_seed_is_idempotent(mongo_uri, monkeypatch, capsys):
    db_name = f"cli_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("OPS_MONGO_URI", mongo_uri)
    monkeypatch.setenv("OPS_MONGO_DB", db_name)
    monkeypatch.setenv("OPS_AUTH_URL", "http://127.0.0.1:9")  # auth unreachable: carry on

    async def count(collection: str) -> int:
        client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
        try:
            return int(await client[db_name][collection].count_documents({}))
        finally:
            await client.close()

    async def prepare() -> None:
        client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
        await seed_orgs(client[db_name])
        await client.close()

    asyncio.run(prepare())
    stations = str(FIXTURES / "stations_bad_rows.csv")
    sensors = str(FIXTURES / "sensors_bad_rows.csv")
    try:
        assert cli.main(["import-stations", stations, "--sensors", sensors]) == 0
        out = capsys.readouterr()
        assert "Stations would be created: 3" in out.out
        assert "Stations row 4 [code]: code is required" in out.out
        assert "Could not refresh organizations" in out.err
        assert asyncio.run(count("stations")) == 0

        assert cli.main(["import-stations", stations, "--sensors", sensors, "--commit"]) == 0
        assert asyncio.run(count("stations")) == 3

        assert cli.main(["seed"]) == 0
        assert cli.main(["seed"]) == 0
        # The fixture already made JM-KIN-001 and JM-MBJ-002: the seed skips them.
        assert asyncio.run(count("stations")) == 3 + 3
        assert cli.main(["import-stations", "missing.csv"]) == 1
    finally:
        async def drop() -> None:
            client: AsyncMongoClient = AsyncMongoClient(mongo_uri)
            await client.drop_database(db_name)
            await client.close()

        asyncio.run(drop())
