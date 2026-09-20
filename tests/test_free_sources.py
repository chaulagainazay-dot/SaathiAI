"""Free market-data agent — HTML parse + derived fields (hermetic, no network)."""
from __future__ import annotations

from saathi.platform.market_data import free_sources as fs

SAMPLE = """
<table><tbody>
<tr><td>1</td><td><a>NABIL</a></td><td>44</td><td>500.00</td><td>515.00</td><td>498.00</td>
<td>512.00</td><td>512.00</td><td>0</td><td>0</td><td>509.00</td><td>1,200</td><td>500.00</td><td>6,10,000</td></tr>
<tr><td>2</td><td>HDL</td><td>48</td><td>1,100.00</td><td>1,210.00</td><td>1,090.00</td>
<td>1,201.00</td><td>1,201.00</td><td>0</td><td>0</td><td>1,150.00</td><td>500</td><td>1,180.00</td><td>6,00,500</td></tr>
</tbody></table>
"""


def test_num_strips_commas_and_handles_blank():
    assert fs._num("1,200.50") == 1200.5
    assert fs._num("-") is None
    assert fs._num("") is None


def test_parse_extracts_rows_and_derives_change():
    rows = fs._parse_sharesansar(SAMPLE)
    assert len(rows) == 2
    nabil = rows[0]
    assert nabil["symbol"] == "NABIL"
    assert nabil["ltp"] == 512.0 and nabil["prev_close"] == 500.0
    assert nabil["change"] == 12.0
    assert round(nabil["percent_change"], 2) == 2.4
    hdl = rows[1]
    assert hdl["symbol"] == "HDL" and hdl["high"] == 1210.0 and hdl["volume"] == 500.0


def test_parse_skips_non_symbol_rows():
    bad = "<table><tbody><tr><td>x</td><td>not a symbol!!</td><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td><td>8</td><td>9</td><td>10</td><td>11</td></tr></tbody></table>"
    assert fs._parse_sharesansar(bad) == []
