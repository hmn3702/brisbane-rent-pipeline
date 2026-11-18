import envconfig


def test_env_local_wins_and_process_env_is_kept(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://from-env/db\nOTHER=a\n")
    (tmp_path / ".env.local").write_text("DATABASE_URL=postgresql://from-env-local/db\n")
    monkeypatch.setattr(envconfig, "ROOT", tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    monkeypatch.setenv("OTHER", "from-process")

    envconfig.load_env()

    assert envconfig.database_url() == "postgresql://from-env-local/db"   # .env.local overrides .env
    import os
    assert os.environ["OTHER"] == "from-process"                            # real env never overridden


def test_unpooled_url_preferred(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x-pooler.neon.tech/db")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://u:p@ep-x.neon.tech/db")
    assert envconfig.database_url() == "postgresql://u:p@ep-x.neon.tech/db"
