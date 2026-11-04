import shortterm_trader.config as config
from shortterm_trader.config import load_settings, redacted_source_status


def test_settings_loads_without_printing_secret(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TUSHARE_TOKEN=secret\nFRED_API_KEY=fred\n", encoding="utf-8")
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    settings = load_settings(root=tmp_path, env_file=env_file)
    status = redacted_source_status(settings)
    assert status["tushare_token"] is True
    assert status["fred_api_key"] is True
    assert settings.intraday_status_path.name == "intraday_status.json"
    assert "secret" not in str(status)


def test_settings_loads_env_without_dotenv_dependency(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("QMT_SDK_PATH=C:\\QMT\\python\\Lib\\site-packages\nQMT_REALTIME_SYMBOLS=000001.SZ,510300.SH\n", encoding="utf-8")
    monkeypatch.delenv("QMT_SDK_PATH", raising=False)
    monkeypatch.delenv("QMT_REALTIME_SYMBOLS", raising=False)
    monkeypatch.setattr(config, "load_dotenv", None)
    settings = load_settings(root=tmp_path, env_file=env_file)
    assert str(settings.qmt_sdk_path).endswith("QMT\\python\\Lib\\site-packages")
    assert settings.qmt_realtime_symbols == ("000001.SZ", "510300.SH")
