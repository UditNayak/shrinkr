from alembic import command


def test_models_match_migrations(alembic_config):
    command.check(alembic_config)
