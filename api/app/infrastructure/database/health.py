from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_database(db_session: AsyncSession) -> bool:
    result = await db_session.execute(text("select 1"))
    return result.scalar_one() == 1
