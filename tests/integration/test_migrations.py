from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_migrations_revisions_chain() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    assert heads[0] == "0002_tokens"

    rev_0002 = script.get_revision("0002_tokens")
    assert rev_0002 is not None
    assert rev_0002.down_revision == "0001_users"

    rev_0001 = script.get_revision("0001_users")
    assert rev_0001 is not None
    assert rev_0001.down_revision is None
