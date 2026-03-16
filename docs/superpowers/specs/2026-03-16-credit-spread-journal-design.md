# Credit Spread Journal Extension

## Goal

Extend `journal.py` to log credit spread trades (call spreads and put spreads) alongside existing swing trades, with proper P&L tracking in both dollars and return-on-risk %.

## CSV Schema Changes

Add 7 columns to `JOURNAL_COLUMNS` (after existing columns, before `notes`):

| Column | Type | Example | Notes |
|--------|------|---------|-------|
| `trade_type` | str | `swing` / `credit_spread` | Blank or missing = `swing` (backward compat) |
| `spread_type` | str | `call` / `put` | Blank for swing trades |
| `short_strike` | float | `672` | Strike sold |
| `long_strike` | float | `674` | Protective strike bought |
| `spread_width` | float | `2.0` | `abs(long_strike - short_strike)` |
| `contracts` | int | `10` | Number of spreads |
| `credit` | float | `0.087` | Net credit received per spread (after commissions) |
| `pnl_dollars` | float | `87.0` | Dollar P&L (stored, not derived). Both trade types. |

No migration needed. Existing rows will have these columns as empty/NaN, which is handled by treating missing `trade_type` as `"swing"`.

## Field Reuse

- `entry_price`: stores the net credit per spread (same value as `credit`, kept for backward compat with existing code that reads this field)
- `exit_price`: stores the debit paid to close per spread (0 if expired OTM)
- `pnl_pct`: stores return-on-risk % for credit spreads, return-on-entry % for swings. These use different denominators and must never be aggregated across trade types.
- `pnl_dollars`: new column, stored (not derived). For credit spreads: `(credit - debit) * contracts * 100`. For swings: `pnl_pct / 100 * size`. Stored because `size` meaning differs between trade types and re-derivation is error-prone.
- `direction`: `"short"` for credit spreads (you're selling premium)
- `size`: max dollar risk for credit spreads (`(spread_width - credit) * contracts * 100`), position size in dollars for swings. Meaning differs by trade type but both answer "how much capital is at risk."
- `ticker`, `date`, `exit_date`, `exit_reason`, `regime`, `breadth_trend`, `notes`: unchanged

## P&L Calculation

For credit spreads:
- `max_risk_per_spread = spread_width - credit`
- `pnl_dollars = (credit - debit) * contracts * 100`
- `pnl_pct = pnl_dollars / (max_risk_per_spread * contracts * 100) * 100` (return on risk)

Example: sell 10x 672/674 call spread for $0.087 net credit, expires worthless:
- `max_risk_per_spread = 2.0 - 0.087 = 1.913`
- `pnl_dollars = (0.087 - 0) * 10 * 100 = $87`
- `pnl_pct = 87 / (1.913 * 10 * 100) * 100 = 4.5%`

For swings: unchanged — `(exit - entry) / entry * 100` for longs, `(entry - exit) / entry * 100` for shorts.

## Interactive Flow

### New entry (`journal.py log` → option 1)

```
Trade type? (1) swing  (2) credit spread

# If credit spread:
Ticker: SPY
Spread type [call/put]: call
Short strike: 672
Long strike: 674
Contracts: 10
Net credit per spread (after commissions): $0.087
Notes (optional): 0DTE, SPY ~669 at entry

# Auto-filled from market data (same as swing):
#   regime, breadth_trend
# Auto-computed:
#   spread_width = abs(674 - 672) = 2.0
#   direction = "short"
#   entry_price = 0.087 (= credit)
#   size = max_risk = (2.0 - 0.087) * 10 * 100 = $1,913
```

### Close trade (`journal.py log` → option 2)

Display open credit spreads as: `2026-03-16 SPY short 672/674C x10 @ $0.087 credit`

```
Exit reason: expired_otm / closed / stop / rolled

# If expired_otm → auto-set debit to 0, skip debit prompt
# Otherwise:
Debit paid per spread: $0.03
```

### Swing trades

Completely unchanged. The `trade_type` prompt is the only new step; choosing "swing" falls through to the existing flow.

## Review Stats

`journal.py review` outputs two sections when both trade types exist:

```
SWING TRADES
  Closed trades:    12
  Win rate:         83.3%
  Avg P&L:          +1.05%
  ...

CREDIT SPREADS
  Closed trades:    8
  Win rate:         87.5%
  Avg P&L ($):      +$74.50/trade
  Avg RoR:          +3.9%/trade
  Total P&L:        +$596.00
  Profit factor:    4.20
  Regime distribution:
    ...
```

If only one trade type exists, show just that section (no empty headers).

## Function Changes

### `close_trade(trade_idx, exit_price, exit_date, exit_reason, notes="", path=...)`

Signature unchanged. Reads `trade_type` from the row to branch P&L:
- If `trade_type` is blank/NaN or `"swing"`: existing logic (`(exit - entry) / entry * 100`)
- If `trade_type == "credit_spread"`: reads `credit`, `spread_width`, `contracts` from the row, computes `pnl_dollars = (credit - exit_price) * contracts * 100`, computes `pnl_pct = pnl_dollars / ((spread_width - credit) * contracts * 100) * 100`

Stores both `pnl_pct` and `pnl_dollars` on the row.

### `compute_review_stats(path=..., trade_type=None)`

Add optional `trade_type` filter. When `None`, returns stats for all trades (backward compat). When `"swing"` or `"credit_spread"`, filters to that type only.

For credit spreads, the returned dict adds: `avg_pnl_dollars`, `total_pnl_dollars`.

### `print_review()`

Calls `compute_review_stats` twice (once per type), prints each section only if trades exist. Never mixes pnl_pct across trade types.

### `add_entry(entry_dict, path=...)`

Signature unchanged. Already dict-based and ignores missing keys — no changes needed. Callers pass the new fields in the dict.

## Files Modified

- `journal.py`: add columns (`pnl_dollars` + 7 credit spread columns), branch `close_trade` P&L, add `trade_type` filter to `compute_review_stats`, split `print_review`, branch `interactive_log`
- `tests/test_journal.py`: add tests for credit spread entry, close (expired_otm + manual debit), P&L math, mixed review stats, backward compat (old rows treated as swing)

## Out of Scope

- Iron condor as a single journal entry (log each side separately for now)
- Greeks tracking (delta, theta at entry)
- Rolling trades (close + reopen is two entries; `rolled` is a valid exit reason for tracking why you closed, not a special workflow)
- Commission tracking as a separate field (user enters net credit)
- Removing redundant `spread_width` column (it's derivable from strikes, but stored for CSV readability)
