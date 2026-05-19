from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.db.session import async_session_factory


async def check_database() -> bool:
    try:
        async with async_session_factory() as session:
            await session.execute(text("select 1"))
        return True
    except SQLAlchemyError:
        return False
