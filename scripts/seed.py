import asyncio
import json
from pathlib import Path
from typing import cast

from sqlalchemy import CursorResult
from sqlalchemy.dialects.postgresql import insert as pg_insert

import app.db.models  # noqa: F401  registers every model onto Base.metadata
from app.db.base import Base
from app.db.session import db

LOCAL_DEV_DATA_DIR = Path(__file__).resolve().parent.parent / "local-dev-data"

# Natural-key column per seeded table, used for ON CONFLICT DO NOTHING so this script
# is safe to run unconditionally on every deploy (deploy.yml runs it against the real
# production DATABASE_URL now, not just CI's throwaway test container - re-running it
# against a database that already has these rows must be a no-op, not a
# UniqueViolation that fails the deploy). Add an entry here for any future
# local-dev-data/*.json fixture that gets seeded.
_NATURAL_KEY_COLUMN = {"team_members": "azure_upn"}


async def seed() -> None:
    seeded_any = False
    async for session in db.get_session():
        for table in Base.metadata.sorted_tables:
            fixture_path = LOCAL_DEV_DATA_DIR / f"{table.name}.json"
            if not fixture_path.exists():
                continue
            rows = json.loads(fixture_path.read_text())
            if not rows:
                continue
            natural_key = _NATURAL_KEY_COLUMN.get(table.name)
            if natural_key is None:
                raise ValueError(
                    f"local-dev-data/{table.name}.json exists but has no entry in "
                    "_NATURAL_KEY_COLUMN - add one so re-seeding stays idempotent."
                )
            stmt = (
                pg_insert(table).values(rows).on_conflict_do_nothing(index_elements=[natural_key])
            )
            # session.execute()'s declared return type doesn't expose .rowcount (it's
            # a CursorResult-only attribute, present at runtime for INSERT/UPDATE/DELETE
            # but not on the generic Result[Any] mypy sees) - the cast just tells mypy
            # what's actually true here, not a behavior change.
            result = cast(CursorResult, await session.execute(stmt))
            print(f"Seeded {result.rowcount} new row(s) into {table.name} ({len(rows)} in fixture)")
            seeded_any = True
        await session.commit()

    if not seeded_any:
        print("No fixture files found in local-dev-data/ - nothing to seed.")


if __name__ == "__main__":
    asyncio.run(seed())
