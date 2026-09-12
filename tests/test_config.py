import pytest

from krillion_bot.config import Config, load_dotenv


def test_load_dotenv_does_not_override_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nDISCORD_TOKEN=from-file\nELO_K='40'\nEMPTY=\n")
    monkeypatch.setenv("DISCORD_TOKEN", "from-env")
    monkeypatch.delenv("ELO_K", raising=False)
    monkeypatch.delenv("EMPTY", raising=False)
    load_dotenv(env)
    import os

    assert os.environ["DISCORD_TOKEN"] == "from-env"
    assert os.environ["ELO_K"] == "40"
    assert os.environ["EMPTY"] == ""


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "abc")
    monkeypatch.setenv("LEADERBOARD_CHANNEL_ID", "")
    monkeypatch.setenv("RESULTS_CHANNEL_ID", "123")
    monkeypatch.setenv("LATE_GRACE_MINUTES", "5")
    monkeypatch.setenv("ELO_K", "40")
    monkeypatch.setenv("ELO_PROVISIONAL_K", "80")
    monkeypatch.setenv("ELO_PROVISIONAL_GAMES", "3")
    cfg = Config.from_env()
    assert cfg.token == "abc"
    assert cfg.leaderboard_channel_id is None
    assert cfg.results_channel_id == 123
    assert cfg.late_grace_minutes == 5
    assert cfg.elo_k == 40
    assert (cfg.provisional_k, cfg.provisional_games) == (80, 3)
    assert str(cfg.puzzle_tz) == "America/New_York"


def test_config_requires_token(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        Config.from_env()
