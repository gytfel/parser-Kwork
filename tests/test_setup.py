import io
import os
from types import SimpleNamespace

import pytest

from kwork_bot import setup_wizard
from kwork_bot.config import ConfigError, MissingTokenError, load_settings
from kwork_bot.setup_wizard import run_setup, update_env_text

TOKEN = "123456789:" + "A" * 35


def test_update_env_text_keeps_comments_and_other_keys():
    text = "# токен\nBOT_TOKEN=\nCHECK_INTERVAL=60\n#ALLOWED_USERS=1\nKWORK_PROXY=http://p\n"
    result = update_env_text(text, {"BOT_TOKEN": "t", "ALLOWED_USERS": "5"})
    assert result == (
        "# токен\nBOT_TOKEN=t\nCHECK_INTERVAL=60\n#ALLOWED_USERS=1\nKWORK_PROXY=http://p\n"
        "ALLOWED_USERS=5\n"
    )


def test_setup_from_arguments_starts_from_example(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO())
    (tmp_path / ".env.example").write_text("# пример\nBOT_TOKEN=\nCHECK_INTERVAL=90\n")
    env = tmp_path / ".env"

    run_setup(token=TOKEN, allowed_users="1, 2", env_file=env)

    assert env.read_text() == f"# пример\nBOT_TOKEN={TOKEN}\nCHECK_INTERVAL=90\nALLOWED_USERS=1,2\n"
    assert env.stat().st_mode & 0o777 == 0o600


def test_setup_without_terminal_requires_token(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO())
    with pytest.raises(ConfigError):
        run_setup(env_file=tmp_path / ".env")


def test_setup_rejects_bad_ids(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO())
    with pytest.raises(ConfigError):
        run_setup(token=TOKEN, allowed_users="@me", env_file=tmp_path / ".env")


def test_interactive_setup_detects_user_id(tmp_path, monkeypatch):
    answers = iter(["", "не токен", TOKEN, "", "д"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))

    async def fake_username(token):
        if token != TOKEN:
            raise setup_wizard.TokenValidationError("bad")
        return "my_kwork_bot"

    async def fake_detect(token):
        return SimpleNamespace(id=777, full_name="Влад", username="vlad")

    monkeypatch.setattr(setup_wizard, "fetch_bot_username", fake_username)
    monkeypatch.setattr(setup_wizard, "detect_user", fake_detect)

    env = tmp_path / ".env"
    run_setup(env_file=env)

    assert f"BOT_TOKEN={TOKEN}" in env.read_text()
    assert "ALLOWED_USERS=777" in env.read_text()


def test_load_settings(tmp_path, monkeypatch):
    # load_dotenv пишет в os.environ — подменяем его, чтобы не задеть другие тесты.
    keys = {"BOT_TOKEN", "ALLOWED_USERS", "CHECK_INTERVAL", "DB_PATH", "KWORK_PROXY"}
    monkeypatch.setattr(os, "environ", {k: v for k, v in os.environ.items() if k not in keys})
    env = tmp_path / ".env"

    env.write_text("BOT_TOKEN=\n")
    with pytest.raises(MissingTokenError):
        load_settings(env)

    env.write_text(f"BOT_TOKEN={TOKEN}\nALLOWED_USERS=1,2\nCHECK_INTERVAL=5\n")
    settings = load_settings(env, override=True)
    assert settings.bot_token == TOKEN
    assert settings.allowed_users == {1, 2}
    assert settings.check_interval == 30  # не чаще минимума
    assert settings.db_path == str(tmp_path / "kwork_bot.db")
    assert settings.kwork_proxy is None
