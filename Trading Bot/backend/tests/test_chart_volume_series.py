from types import SimpleNamespace
import pandas as pd

from app.chart_terminal import ChartTerminal


def test_saved_volume_spans_expiries_without_summing_or_patching_contract_gaps(monkeypatch):
    near = dict(symbol='NIFTY', contract_id='NSE:1', security_id='1', exchange='NSE',
                expiry='2026-09-29', identity_verified=True)
    far = {**near, 'contract_id': 'NSE:2', 'security_id': '2', 'expiry': '2026-10-27'}
    def frame(day, volume):
        return pd.DataFrame(dict(timestamp=pd.date_range(day + ' 09:15', periods=10, freq='min', tz='Asia/Kolkata'),
                                 symbol='NIFTY', open=100., high=102., low=99., close=101., volume=volume))
    first = pd.concat([frame('2026-09-25', 10), frame('2026-09-28', 10).drop(index=2)])
    second = pd.concat([frame('2026-09-25', 100), frame('2026-09-28', 100), frame('2026-10-01', 100)])
    terminal = ChartTerminal(SimpleNamespace(list_records=lambda *args: [near, far, far]), None, None)
    monkeypatch.setattr(terminal, '_volume_history', lambda *args: (far, second, None))
    monkeypatch.setattr(terminal, '_history', lambda *args: first)
    now = pd.Timestamp('2026-10-05T08:00:00+05:30')
    _, series, _ = terminal._volume_series('NIFTY', now, {})
    bars = terminal.volume_bars(series, now, 'NIFTY', 5)
    assert [bar['value'] for bar in bars] == [50, 50, 50, 500, 500]
    assert [bar['contract_id'] for bar in bars] == ['NSE:1', 'NSE:1', 'NSE:1', 'NSE:2', 'NSE:2']
    # The missing 09:17 minute must not be supplied by the overlapping far expiry.
    assert not any(pd.Timestamp(bar['time'], unit='s', tz='UTC').tz_convert('Asia/Kolkata').isoformat().startswith('2026-09-28T09:15') for bar in bars)
    assert len(series) == 29
