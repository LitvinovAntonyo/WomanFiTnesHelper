from pathlib import Path

from app.config import Settings


def test_allowed_ids_are_parsed_from_env_style_string(monkeypatch):
    monkeypatch.setenv("ALLOWED_TELEGRAM_IDS", "10, 20")
    settings = Settings(
        telegram_bot_token="123456:token",
        _env_file=None,
    )
    assert settings.allowed_telegram_ids == [10, 20]
    assert settings.is_telegram_user_allowed(10)
    assert not settings.is_telegram_user_allowed(30)


def test_database_path_is_extracted():
    settings = Settings(database_url="sqlite+aiosqlite:///data/test.sqlite3")
    assert settings.database_path == Path("data/test.sqlite3")


def test_reset_button_setting_can_be_disabled_from_environment(monkeypatch):
    monkeypatch.setenv("SHOW_RESET_BUTTON", "false")

    settings = Settings(_env_file=None)

    assert settings.show_reset_button is False


def test_gift_mode_settings_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("CLAIM_FIRST_USER", "true")
    monkeypatch.setenv("GIFT_RECIPIENT_NAME", "Ангелина")

    settings = Settings(_env_file=None)

    assert settings.claim_first_user is True
    assert settings.gift_recipient_name == "Ангелина"
