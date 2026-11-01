import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from tests.factories import make_user


@pytest.mark.asyncio
async def test_create_and_retrieve_user(db_session: AsyncSession) -> None:
    user = make_user(email="elena.rostova@sovcom.internal", full_name="Elena Rostova")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.email == "elena.rostova@sovcom.internal"
    assert user.is_active is True
    assert user.is_superuser is False
    assert user.failed_login_count == 0
    assert user.created_at is not None

    stmt = select(User).where(User.email == "elena.rostova@sovcom.internal")
    result = await db_session.execute(stmt)
    persisted = result.scalar_one()
    assert persisted.id == user.id
    assert persisted.full_name == "Elena Rostova"


@pytest.mark.asyncio
async def test_user_email_unique_constraint(db_session: AsyncSession) -> None:
    first = make_user(email="duplicate.test@nexus-security.io")
    second = make_user(email="duplicate.test@nexus-security.io")

    db_session.add(first)
    await db_session.commit()

    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_user_email_case_insensitive_unique_constraint(db_session: AsyncSession) -> None:
    first = make_user(email="case.check@nexus-security.io")
    second = make_user(email="CASE.CHECK@nexus-security.io")

    db_session.add(first)
    await db_session.commit()

    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
