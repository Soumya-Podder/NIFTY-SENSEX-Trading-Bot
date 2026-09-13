# Backtest and dashboard audit — 13 September 2026

## Verified defects and corrections

1. **Stale report selection.** The dashboard selected the latest report only once on initial load. An externally completed job could leave an invalidated legacy report selected. The page now follows new latest reports unless the user explicitly selects history; a newer-report button preserves manual selection.
2. **History and report status disagreed.** Legacy job records retained `complete` even when their report was invalidated. A reviewed-history endpoint now supplies the report evidence state and withholds invalid/incomplete performance. Invalidated history is optional in the default view.
3. **Net/Gross presentation was inconsistent.** The research engine calculated estimated net P&L, while assumptions and form/trade descriptions said net results were unavailable. Those descriptions are reconciled. New research runs save an independent gross equity series and gross metrics; the toggle changes the series, statistics, calendar and final capital together. Old missing series remain unavailable.
4. **Partial reports could look usable.** Eligibility previously accepted the `research_net` quality without requiring completed status. Partial runs are now explicitly blocked from headline performance; diagnostic observations remain in the audit report.
5. **Five-year preset boundary differed from downloader.** The preset subtracted five years from yesterday; the downloader used five years from today. Automatic Dhan five-year requests now record the original request, start at the downloader boundary and explain the unavailable endpoint date.
6. **Misleading calendar.** The UI previously manufactured a five-calendar-year display even for a seven-day report. It now displays years intersecting the actual request, including both partial endpoint years when a rolling five-year span crosses six calendar years.
7. **Wrong research target metadata.** The generic metrics default was ₹1,200. New research metrics now use the configured ₹1,000 target.
8. **Invalid startup settings.** The project `.env` had three open positions, ₹1,000 daily loss, ₹1,800 correlated risk and ₹1,350 target. These conflicted with persistent requirements and prevented Settings validation. Restored one position, ₹800 daily loss/halt, ₹600 correlated/per-trade risk and ₹1,000 net target; credential fields were untouched.
9. **Changes were not active together.** Restarted the backend after verifying zero open paper positions and zero active jobs. Verified the new API and risk settings after restart. The frontend production build passes and its development server serves the updated page.

## Running-system verification

- Full backend test suite: **180 passed**. Subsequent targeted replay/presentation checks: **22 passed** (overlap, not additional distinct tests).
- Frontend TypeScript and Vite production build: passed.
- Browser verified new history, automatically selected completed report, populated Net/Gross charts, differing gross/net profit factors, capital totals and observed range.
- Direct entry: `http://127.0.0.1:5174/#backtest`.
- Fresh cached run `db968416-e0d6-40a5-b9df-cfbc25f0ab44`: ORB retest NIFTY/SENSEX, requested 6–12 September 2026, five observed sessions 7–11 September, 2 trades, 1 win/1 loss, gross -₹157, estimated charges ₹123.82, net -₹280.82, final net capital ₹29,719.18. Both equity series contain 1,755 recorded points. Research, not verified exchange execution or a proven edge.
- Full-range cached run `431a7b8c-9b97-4791-af36-297ffdb0d4ea`: requested five-year preset, effective 13 September 2021–12 September 2026. Still running when this audit was written; inspect the persisted job for current status. No five-year return is claimed here.

## Remaining evidence limits

- Download completion is not complete historical coverage: the completed pass contained 10,285 populated and 3,449 empty responses.
- The Dhan rolling replay is an ORB baseline with current-lot sizing and estimated charges. It is not an exact-contract, dated-lot/fee, historical bid/ask replay of all portfolio strategies.
- Trend pullback, range rejection and combined portfolio replay require the separately supported observed exact-contract CSV path. Underlying-only NIFTY/SENSEX CSVs do not satisfy that requirement.
- Historical learning/promotion and future profitability are not established by the above replay. No positive-return or daily-profit guarantee is inferred.
- The ongoing five-year run must be assessed on its final coverage, unresolved contracts and evidence state; a partial result is not a five-year performance result.
