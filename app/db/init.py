"""Compatibility entrypoint: apply all versioned migrations, including loans."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
