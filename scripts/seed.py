import asyncio
import json
from pathlib import Path

import app.db.models  # noqa: F401  registers every model onto Base.metadata
from app.db.base import Base
from app.db.session import db

LOCAL_DEV_DATA_DIR = Path(__file__).resolve().parent.parent / "local-dev-data"


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
            await session.execute(table.insert(), rows)
            print(f"Seeded {len(rows)} row(s) into {table.name}")
            seeded_any = True
        await session.commit()

    if not seeded_any:
        print("No fixture files found in local-dev-data/ - nothing to seed.")


if __name__ == "__main__":
    asyncio.run(seed())
