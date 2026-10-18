from alembic import command


def test_models_match_migrations(alembic_config):
    # Fails if a model was changed without writing a migration for it.
    command.check(alembic_config)
