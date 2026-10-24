"""Repository-wide invariants for the Alembic revision graph."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_revision_graph_has_one_head(monkeypatch) -> None:
    alembic_dir = (
        Path(__file__).resolve().parents[4] / "openrag" / "services" / "persistence" / "migrations" / "alembic"
    )
    monkeypatch.syspath_prepend(str(alembic_dir))
    config = Config(str(alembic_dir / "alembic.ini"))
    config.set_main_option("script_location", str(alembic_dir))

    heads = ScriptDirectory.from_config(config).get_heads()

    # Fork: c6bd76e44f0c merges the partition is_public branch (via d7e8f9a0b1c2)
    # into upstream's 2.3.2 head 5e6d7c8b9a01.
    assert heads == ["c6bd76e44f0c"]
