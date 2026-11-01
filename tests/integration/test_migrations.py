import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_migrations_revisions_chain() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    assert heads[0] == "0007_audit"

    rev_0007 = script.get_revision("0007_audit")
    assert rev_0007 is not None
    assert rev_0007.down_revision == "0006_shares"

    rev_0006 = script.get_revision("0006_shares")
    assert rev_0006 is not None
    assert rev_0006.down_revision == "0005_versions"

    rev_0005 = script.get_revision("0005_versions")
    assert rev_0005 is not None
    assert rev_0005.down_revision == "0004_documents"

    rev_0004 = script.get_revision("0004_documents")
    assert rev_0004 is not None
    assert rev_0004.down_revision == "0003_workspaces"

    rev_0003 = script.get_revision("0003_workspaces")
    assert rev_0003 is not None
    assert rev_0003.down_revision == "0002_tokens"

    rev_0002 = script.get_revision("0002_tokens")
    assert rev_0002 is not None
    assert rev_0002.down_revision == "0001_users"

    rev_0001 = script.get_revision("0001_users")
    assert rev_0001 is not None
    assert rev_0001.down_revision is None


def test_alembic_upgrade_downgrade_cycle() -> None:
    """Verify migrations apply cleanly to head, revert to base, and re-apply cleanly."""
    db_url = os.environ.get("SECURE_DOCS_TEST_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url or "sqlite" in db_url:
        pytest.skip("Migration cycle test requires PostgreSQL database")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)

    # 1. Apply to head
    command.upgrade(config, "head")

    # 2. Downgrade to base
    command.downgrade(config, "base")

    # 3. Re-apply to head
    command.upgrade(config, "head")
