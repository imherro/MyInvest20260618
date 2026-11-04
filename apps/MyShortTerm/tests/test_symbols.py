from shortterm_trader.symbols import from_baostock_code, is_a_share, to_baostock_code


def test_a_share_symbol_conversion() -> None:
    assert is_a_share("000001.SZ")
    assert to_baostock_code("600000.SH") == "sh.600000"
    assert from_baostock_code("sz.000001") == "000001.SZ"


def test_non_a_share() -> None:
    assert not is_a_share("SPY")

