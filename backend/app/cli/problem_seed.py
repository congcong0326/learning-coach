from __future__ import annotations

import asyncio

from backend.app.core.config import settings
from backend.app.db.session import async_session_factory
from backend.app.services.problem_seed import import_problem_seed


async def _main() -> None:
    async with async_session_factory() as session:
        stats = await import_problem_seed(settings.problem_seed_path, session)
    print(
        "Problem seed import completed: "
        f"{stats.inserted_problems} problems, "
        f"{stats.inserted_categories} categories, "
        f"{stats.inserted_category_items} category items inserted"
    )


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
