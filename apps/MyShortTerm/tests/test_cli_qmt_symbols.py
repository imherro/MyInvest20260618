import pytest

from shortterm_trader.cli import _qmt_symbols


def test_qmt_symbols_accepts_commas_and_spaces() -> None:
    assert _qmt_symbols("000001.SZ,510300.SH", ()) == ["000001.SZ", "510300.SH"]
    assert _qmt_symbols("000001.SZ 510300.SH", ()) == ["000001.SZ", "510300.SH"]
    assert _qmt_symbols("000001.SZ;510300.SH", ()) == ["000001.SZ", "510300.SH"]


def test_qmt_symbols_uses_defaults() -> None:
    assert _qmt_symbols(None, ("000001.SZ",)) == ["000001.SZ"]


def test_qmt_symbols_requires_value() -> None:
    with pytest.raises(SystemExit):
        _qmt_symbols("", ())
