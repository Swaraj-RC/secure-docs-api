from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_migrations_revisions_chain() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    assert heads[0] == "0005_versions"

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
