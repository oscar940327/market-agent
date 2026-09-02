# Portfolio Phase 0 Product Contract

Status: `ready_for_qa`

Last updated: `2026-08-28`

Owner: `Developer Codex`

Review flow: `Developer -> PM Codex -> Reviewer/QA`

## 1. Scope and normative language

This document is the executable product and backend contract for Portfolio Phase 0. It fixes the semantics, schema shape, authorization boundary, atomic write behavior, API behavior, migration strategy, and test matrix that later phases must implement.

No migration, endpoint, store function, or production schema change is authorized by this document. Phase 1 may start only after PM Codex and Reviewer/QA approve this contract.

The words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative.

In scope:

- `portfolios`
- `portfolio_holdings`
- `portfolio_transactions`
- `investment_decisions`
- the future boundary of `portfolio_alerts`
- authentication, ownership, RLS, idempotency, atomic writes, API errors, migration sequencing, and tests

Out of scope:

- broker APIs and automatic order placement
- options, short selling, leverage, and full multi-currency accounting
- tax lot matching, FIFO/LIFO/specific-lot tax reporting
- dividends, stock splits, mergers, and symbol-change processing
- new ML models
- alert evaluation implementation

## 2. Fixed domain semantics

### 2.1 Portfolio

A Portfolio is an owner-scoped container for investment records. It defines the ownership boundary, display name, base currency, and accounting timezone. It is not an analysis report and is not inferred from an inline holdings request.

### 2.2 Holding

A Holding is the current materialized projection for one `portfolio + ticker`. It contains only the currently open quantity and moving-average cost. It is derived exclusively from committed Transaction events.

- A Holding is current state, not history.
- A Holding MUST NOT be directly created, edited, or deleted by a client.
- A Holding with zero quantity MUST NOT remain in `portfolio_holdings`.
- Market price, market value, weight, and unrealized P/L are query-time calculations and MUST NOT become the accounting source of truth.
- Transaction history remains authoritative if the projection must be rebuilt.

### 2.3 Transaction

A Transaction is an immutable, actually executed accounting event. It records the actual quantity, price, fees, currency, trade date, timestamp, and resulting holding projection.

- Normal client transaction types are `buy`, `sell`, and `opening_balance`.
- `reversal` is created only by the dedicated correction RPC.
- A Transaction MUST NOT represent an unfilled planned action.
- A committed Transaction MUST NOT be updated or deleted.

### 2.4 Investment Decision

An Investment Decision records what the owner planned or chose, why, and what information was available at that time. A Decision does not change a Holding.

Supported actions are `hold`, `buy`, `reduce`, `exit`, and `ignore_alert`.

- One Decision MAY have zero, one, or many linked Transactions.
- One Transaction MAY link to at most one Decision.
- `hold` and `ignore_alert` normally have no Transaction.
- Execution progress is derived from linked Transactions and MUST NOT overwrite the original Decision context.

### 2.5 Planned action versus actual execution

Example:

```text
Decision: reduce NVDA by 25 shares because position weight is too high
    -> Transaction A: sell 10 shares at 140.00
    -> Transaction B: sell 5 shares at 142.00
    -> derived execution: partially_executed, 15/25 filled, 10 remaining
```

Only the 15 actually sold shares change the Holding. The unfilled 10 shares never become a Transaction.

Decision state has two independent dimensions:

- `lifecycle_status` is stored as `active`, `cancelled`, or `expired`.
- `execution_state` is derived as `not_applicable`, `planned`, `partially_executed`, `executed`, or `over_executed`.

Only effective, non-reversal `buy`/`sell` Transactions whose `decision_id` equals the Decision are counted. Standalone Transactions, reversed Transactions, reversal events, and opening-balance events are not counted.

Execution-state algorithm:

- `hold` or `ignore_alert`: always `not_applicable`; planned quantity and linked Transactions are forbidden.
- `buy`: count effective linked `buy` quantity.
- `reduce`: count effective linked `sell` quantity.
- `exit` with `planned_quantity`: count effective linked `sell` quantity against that quantity.
- For `buy`, `reduce`, or quantified `exit`: zero fill is `planned`; fill below plan is `partially_executed`; equal fill is `executed`; fill above plan is `over_executed`.
- `exit` with `planned_quantity = null`: zero linked effective sell is `planned`; a linked effective sell whose stored `holding_quantity_after` is greater than zero is `partially_executed`; a linked effective sell whose stored after quantity is zero makes the Decision `executed` permanently unless that sell is later reversed.
- Reversing a linked fill removes it from effective fill quantity and MAY move execution state backward from `executed` to `partially_executed` or `planned`. The original Decision context remains immutable.
- `cancelled` and `expired` never replace execution state. For example, a cancelled Decision may have `execution_state=partially_executed`.

## 3. Shared schema conventions

- PostgreSQL/Supabase is the authoritative persistence layer.
- UUIDs use `uuid` with `gen_random_uuid()` where server-generated.
- Share quantities use `numeric(28,8)`. This supports fractional shares and avoids binary floating-point accounting.
- Prices, average costs, and fees use `numeric(20,8)`.
- Decimal scale is validated before any cast, quantization, fingerprinting, or database write. More than eight submitted fractional digits are rejected; values are never silently rounded to fit scale.
- API decimal request fields accept canonical decimal strings only. JSON numbers, exponent notation, `NaN`, and infinity are rejected. Responses use fixed-scale decimal strings.
- API validators first match `^(0|[1-9][0-9]*)(\.[0-9]{1,8})?$`, then check precision and sign, then pass the original canonical string to RPC.
- Quantity permits at most 20 integer digits plus 8 fractional digits. Price and fee permit at most 12 integer digits plus 8 fractional digits.
- Numeric RPC inputs are `text`, validate format/scale/precision inside PostgreSQL, and only then cast to the target numeric type. Declaring RPC inputs as `numeric(…,8)` is forbidden because PostgreSQL may round during function argument coercion before validation.
- Currency fields use uppercase `char(3)`. Phase 1 is USD-only: DB table checks require `base_currency = 'USD'`, `currency = 'USD'`, and `fee_currency = 'USD'`; RPC repeats the same invariant before insert.
- Tickers use uppercase `varchar(12)` and match `^[A-Z0-9][A-Z0-9.-]{0,11}$`.
- User-supplied text is trimmed. Empty text is invalid when the field is required.
- User timestamps use `timestamptz`; database creation timestamps use `now()`.
- All owner-scoped child tables carry both `owner_id` and `portfolio_id`. This deliberate denormalization enables explicit composite foreign keys, idempotency scope, and simple RLS checks.
- No child row may reference a Portfolio belonging to another owner.
- Existing `tickers` cannot be used as a single-column foreign key because it is unique by `(ticker, universe)`, not by `ticker` alone. Portfolio ticker fields therefore use validation constraints without an FK to `tickers`.

## 4. Complete data model

### 4.1 `portfolios`

| Field | Type / precision | Nullable | Default | Validation | Unique | Foreign key |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | server-generated | primary key; also `unique(owner_id, id)` | none |
| `owner_id` | `uuid` | no | none | derived from verified `auth.uid()`; never accepted from request body | part of `unique(owner_id, id)` | `auth.users(id) on delete restrict` |
| `name` | `varchar(80)` | no | none | trimmed length 1-80 | no | none |
| `base_currency` | `char(3)` | no | `'USD'` | DB CHECK `base_currency = 'USD'`; RPC also rejects every other currency | no | none |
| `timezone` | `varchar(64)` | no | `'UTC'` | valid IANA timezone, checked by API/RPC | no | none |
| `status` | `varchar(16)` | no | `'active'` | `active` or `archived` | no | none |
| `created_at` | `timestamptz` | no | `now()` | server-written | no | none |
| `updated_at` | `timestamptz` | no | `now()` | server-written on mutation | no | none |

Deletion contract:

- Phase 1 exposes archive, not hard delete.
- Archive changes only `status` and `updated_at`; it does not alter Holdings, Transactions, Decisions, or historical snapshots.
- Archived Portfolio reads remain available to the owner.
- New Transactions, opening balances, reversals, and Decisions are rejected with `409 portfolio_archived`. To correct an archived Portfolio, the owner must restore it first through the lifecycle RPC.
- A same-key/same-payload idempotent replay remains readable with `200` after archive because it performs no accounting mutation. A new key or conflicting payload is rejected.
- Phase 1 exposes no hard-delete endpoint, including for an empty Portfolio.
- Direct hard delete is denied by grants/RLS, and child FKs use `on delete restrict`.
- Auth-user deletion is restricted while owned Portfolio records exist. Account erasure requires a separately approved export/retention process and forward migration; it never cascades silently.
- Child foreign keys use `on delete restrict`.

### 4.2 `investment_decisions`

This table is part of the approved data contract but is scheduled for Phase 2, not Phase 1.

| Field | Type / precision | Nullable | Default | Validation | Unique | Foreign key |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | server-generated | primary key; `unique(owner_id, portfolio_id, id)` | none |
| `owner_id` | `uuid` | no | none | derived from verified auth identity | part of scoped keys | with `portfolio_id` -> `portfolios(owner_id, id) on delete restrict` |
| `portfolio_id` | `uuid` | no | none | owner must have access | part of scoped keys | with `owner_id` -> `portfolios(owner_id, id) on delete restrict` |
| `idempotency_key` | `uuid` | no | none | client-generated UUID | `unique(owner_id, portfolio_id, idempotency_key)` | none |
| `request_fingerprint` | `char(64)` | no | none | server SHA-256 of normalized business payload | no | none |
| `ticker` | `varchar(12)` | no | none | uppercase ticker pattern | no | none |
| `action` | `varchar(20)` | no | none | `hold`, `buy`, `reduce`, `exit`, `ignore_alert` | no | none |
| `planned_quantity` | `numeric(28,8)` | yes | `null` | pre-cast scale <= 8 and precision <= 28; if present, `> 0`; required for `buy`/`reduce`; forbidden for `hold`/`ignore_alert`; optional for `exit`, where null means all | no | none |
| `reason` | `varchar(4000)` | no | none | trimmed, non-empty | no | none |
| `thesis` | `text` | yes | `null` | maximum 10,000 characters at API boundary | no | none |
| `risk_conditions` | `jsonb` | no | `'{}'::jsonb` | JSON object only; maximum serialized size 32 KiB | no | none |
| `context_snapshot` | `jsonb` | no | `'{}'::jsonb` | immutable JSON object; maximum 128 KiB; no secrets or full raw reports | no | none |
| `decided_at` | `timestamptz` | no | none | explicit event time; not more than 5 minutes in the future | no | none |
| `expires_at` | `timestamptz` | yes | `null` | must be later than `decided_at` | no | none |
| `lifecycle_status` | `varchar(16)` | no | `'active'` | `active`, `cancelled`, `expired` | no | none |
| `cancelled_at` | `timestamptz` | yes | `null` | required only when lifecycle status is `cancelled` | no | none |
| `cancellation_reason` | `varchar(1000)` | yes | `null` | required and non-empty when lifecycle status is `cancelled` | no | none |
| `created_at` | `timestamptz` | no | `now()` | server-written | no | none |
| `updated_at` | `timestamptz` | no | `now()` | changes only through lifecycle RPC | no | none |

Decision immutability:

- `ticker`, `action`, planned quantity, reason, thesis, risk conditions, context snapshot, and `decided_at` are immutable after insert.
- Only lifecycle fields may change through a dedicated RPC.
- Execution state is derived; it is not stored in `lifecycle_status` or another column.

### 4.3 `portfolio_transactions`

| Field | Type / precision | Nullable | Default | Validation | Unique | Foreign key |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | server-generated | primary key; `unique(owner_id, portfolio_id, id)` | none |
| `owner_id` | `uuid` | no | none | derived from verified auth identity | part of scoped keys | with `portfolio_id` -> `portfolios(owner_id, id) on delete restrict` |
| `portfolio_id` | `uuid` | no | none | owner must have access | part of scoped keys | with `owner_id` -> `portfolios(owner_id, id) on delete restrict` |
| `idempotency_key` | `uuid` | no | none | client-generated UUID | `unique(owner_id, portfolio_id, idempotency_key)` | none |
| `request_fingerprint` | `char(64)` | no | none | server SHA-256 of normalized payload | no | none |
| `transaction_type` | `varchar(20)` | no | none | `buy`, `sell`, `opening_balance`, `reversal` | no | none |
| `ticker` | `varchar(12)` | no | none | uppercase ticker pattern | no | none |
| `quantity` | `numeric(28,8)` | no | none | pre-cast scale <= 8 and precision <= 28; `> 0`; absolute executed quantity | no | none |
| `price` | `numeric(20,8)` | no | none | pre-cast scale <= 8 and precision <= 20; `> 0`; actual execution price or imported average cost | no | none |
| `currency` | `char(3)` | no | `'USD'` | DB CHECK `currency = 'USD'`; RPC repeats invariant | no | none |
| `fees` | `numeric(20,8)` | no | `0` | pre-cast scale <= 8 and precision <= 20; `>= 0` | no | none |
| `fee_currency` | `char(3)` | no | `'USD'` | DB CHECK `fee_currency = 'USD'`; RPC repeats invariant | no | none |
| `trade_date` | `date` | no | none | explicit broker/accounting date; cannot be in the future relative to Portfolio timezone | no | none |
| `executed_at` | `timestamptz` | no | none | explicit timestamp with timezone; cannot be more than 5 minutes in the future | no | none |
| `decision_id` | `uuid` | yes | `null` | target-model field added only by migration `018`; must match owner, portfolio, ticker, and compatible action | no | added only by `018`: `(owner_id, portfolio_id, decision_id)` -> `investment_decisions(owner_id, portfolio_id, id) on delete restrict` |
| `execution_group_id` | `uuid` | yes | `null` | groups multiple fills of one manual plan/order; not an order record | no | none |
| `reversal_of_transaction_id` | `uuid` | yes | `null` | required only for `reversal`; original cannot itself be a reversal | partial unique where non-null | self-FK `(owner_id, portfolio_id, reversal_of_transaction_id)` -> scoped transaction key, `on delete restrict` |
| `correction_group_id` | `uuid` | yes | `null` | groups a reversal and replacement transaction | no | none |
| `note` | `varchar(2000)` | yes | `null` | trimmed; reversal requires a non-empty reason | no | none |
| `position_delta` | `numeric(28,8)` | no | none | RPC-derived signed effect: positive buy/opening, negative sell, inverse for reversal | no | none |
| `holding_quantity_before` | `numeric(28,8)` | no | none | RPC snapshot, `>= 0` | no | none |
| `holding_quantity_after` | `numeric(28,8)` | no | none | RPC snapshot, `>= 0` | no | none |
| `average_cost_before` | `numeric(20,8)` | yes | `null` | null only when no prior open Holding | no | none |
| `average_cost_after` | `numeric(20,8)` | yes | `null` | null only after a full close | no | none |
| `ticker_sequence` | `bigint` | no | none | RPC-assigned, strictly increasing per owner/Portfolio/ticker and never reset after close/reopen; also the original response's Holding version | `unique(owner_id, portfolio_id, ticker, ticker_sequence)` | none |
| `created_at` | `timestamptz` | no | `now()` | immutable server timestamp | no | none |

Additional constraints:

- Non-reversal rows require `reversal_of_transaction_id is null`.
- Reversal rows require `reversal_of_transaction_id is not null` and a non-empty note.
- `opening_balance` requires `fees = 0`, `decision_id is null`, and no prior effective event for that ticker.
- A unique partial index on `reversal_of_transaction_id` prevents reversing one Transaction twice.
- Normal and reversal events receive the next `ticker_sequence` under the Portfolio lock. Ordering by timestamps or UUID is forbidden for reversal logic.
- Direct table `INSERT`, `UPDATE`, and `DELETE` grants are not given to `authenticated`; writes occur only through approved RPC functions.

### 4.4 `portfolio_holdings`

| Field | Type / precision | Nullable | Default | Validation | Unique | Foreign key |
| --- | --- | --- | --- | --- | --- | --- |
| `owner_id` | `uuid` | no | none | copied from verified auth identity by RPC | composite primary key | with `portfolio_id` -> `portfolios(owner_id, id) on delete restrict` |
| `portfolio_id` | `uuid` | no | none | owner must have access | composite primary key | with `owner_id` -> `portfolios(owner_id, id) on delete restrict` |
| `ticker` | `varchar(12)` | no | none | uppercase ticker pattern | composite primary key `(owner_id, portfolio_id, ticker)` | none |
| `quantity` | `numeric(28,8)` | no | none | `> 0`; zero rows are deleted | no | none |
| `average_cost` | `numeric(20,8)` | no | none | `> 0` | no | none |
| `last_transaction_id` | `uuid` | no | none | latest projection-producing event, normal or reversal; staged nullable without FK in `016`, then made non-null by `017` before writes are enabled | no | added only by `017`: `(owner_id, portfolio_id, last_transaction_id)` -> `portfolio_transactions(owner_id, portfolio_id, id) on delete restrict` |
| `version` | `bigint` | no | none | `> 0`; equals the latest committed Transaction `ticker_sequence` and never resets after close/reopen | no | none |
| `created_at` | `timestamptz` | no | `now()` | server-written | no | none |
| `updated_at` | `timestamptz` | no | `now()` | server-written by transaction RPC | no | none |

`cost_basis_total` is returned as `quantity * average_cost` and is not persisted, preventing redundant values from drifting.

### 4.5 Future `portfolio_alerts` boundary

Alerts are reserved for Phase 3 and MUST NOT be created by Phase 1 or Phase 2 migrations.

The future minimum shape is:

| Field | Type / precision | Nullable | Default | Validation | Unique | Foreign key |
| --- | --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | no | `gen_random_uuid()` | server-generated | primary key; `unique(owner_id, portfolio_id, id)` | none |
| `owner_id` | `uuid` | no | none | verified owner | part of scoped keys | with `portfolio_id` -> `portfolios(owner_id, id) on delete restrict` |
| `portfolio_id` | `uuid` | no | none | owner must have access | part of scoped keys | with `owner_id` -> `portfolios(owner_id, id) on delete restrict` |
| `ticker` | `varchar(12)` | yes | `null` | uppercase pattern when present; null means portfolio-level alert | no | none |
| `alert_type` | `varchar(50)` | no | none | controlled Phase 3 value | no | none |
| `severity` | `varchar(16)` | no | none | `low`, `medium`, `high`, `critical` | no | none |
| `status` | `varchar(20)` | no | `'open'` | `open`, `acknowledged`, `resolved`, `dismissed` | part of active dedupe condition | none |
| `dedupe_key` | `varchar(128)` | no | none | trimmed, non-empty | partial unique `(owner_id, portfolio_id, dedupe_key)` while status is `open`/`acknowledged` | none |
| `evidence` | `jsonb` | no | `'{}'::jsonb` | immutable JSON object with source timestamps; maximum 128 KiB | no | none |
| `data_as_of` | `timestamptz` | no | none | evidence freshness time | no | none |
| `triggered_at` | `timestamptz` | no | none | explicit event time | no | none |
| `resolved_at` | `timestamptz` | yes | `null` | required only when resolved | no | none |
| `created_at` | `timestamptz` | no | `now()` | server-written | no | none |
| `updated_at` | `timestamptz` | no | `now()` | lifecycle updates only | no | none |

Alert boundary rules:

- An Alert never creates a Transaction, changes a Holding, or places an order.
- Phase 3 may add nullable `source_alert_id` to `investment_decisions` using a composite owner/portfolio FK.
- A Decision captures the Alert evidence in its immutable context snapshot so later Alert lifecycle changes do not rewrite history.
- Alert generation and deduplication are separate from the transaction RPC.

## 5. Transaction accounting rules

### 5.1 Buy and opening balance

For an existing Holding:

```text
new_quantity = old_quantity + buy_quantity
new_cost_basis = old_quantity * old_average_cost
                 + buy_quantity * price
                 + fees
new_average_cost = new_cost_basis / new_quantity
```

All intermediate arithmetic uses unconstrained PostgreSQL `numeric`. Submitted quantity, price, and fee values are validated before cast and are never rounded. A newly derived average cost is explicitly rounded once with `round(value, 8)` immediately before the Holding write; this derived-value rounding is deterministic and is not used to make an invalid request acceptable.

For a first buy, old quantity and old cost basis are zero.

`opening_balance` is a one-time event for importing a current position:

- `quantity` is the current opening quantity.
- `price` is the imported moving-average cost per share.
- `fees` MUST be zero because imported average cost already represents the opening basis.
- `trade_date` and `executed_at` mean the balance as-of date/time, not a claimed historical broker fill.
- It is accepted only when the ticker has no current Holding and no unreversed prior Transaction history in that Portfolio.
- It is not expanded into fabricated historical lots.

### 5.2 Sell

- Sell quantity MUST be positive.
- Sell quantity MUST NOT exceed the current Holding quantity.
- Remaining quantity is `old_quantity - sell_quantity`.
- Average cost remains unchanged on a partial sell.
- Sell fees affect proceeds but do not alter the remaining Holding average cost.
- If remaining quantity is zero, the Holding row is deleted.
- Realized P/L reporting is not part of Phase 1, but the immutable event data is sufficient for later moving-average P/L calculation.

### 5.3 Fractional shares

- Up to eight decimal places are accepted.
- Zero is rejected. More than eight submitted fractional digits are rejected before any rounding or cast, even when the extra digits are trailing zeros.
- API and domain code MUST use Decimal, never binary float, for accounting operations.

### 5.4 Trade date and timestamp

- `trade_date` is the explicit broker/accounting calendar date in the Portfolio timezone.
- `executed_at` is the best-known execution/as-of timestamp with an explicit timezone offset.
- `created_at` is when Market Agent recorded the event and is server-generated.
- `trade_date` is never derived from current market data and is never overwritten.
- Future values are rejected except for at most five minutes of timestamp clock skew.

### 5.5 Partial fills

- Each actual fill is one Transaction with its own idempotency key.
- Fills MAY share `execution_group_id` and `decision_id`.
- There is no Order table in the first version.
- Planned but unfilled quantity exists only on the Decision.

### 5.6 Reversal and correction

Transactions are append-only. A correction is:

1. a `reversal` event created by `reverse_portfolio_transaction`, then
2. an optional corrected `buy`, `sell`, or `opening_balance` event with a new idempotency key.

Reversal rules:

- The client supplies only portfolio ID, original transaction ID, reversal idempotency key, reason, correction group ID, and reversal timestamp.
- Quantity, price, currencies, fees, ticker, and inverse projection snapshots are copied/derived by the database.
- Only the latest effective normal Transaction for that ticker may be reversed. This keeps projection reversal deterministic and prevents retroactive invalidation of later effective events.
- An already reversed Transaction or a reversal Transaction cannot be reversed.
- Reversal restores the original Transaction's exact `holding_quantity_before` and `average_cost_before` snapshot.
- Reversing a first/opening event removes the Holding if the restored quantity is zero.
- A correction that is not the latest effective normal event requires reversing later effective normal events in strict reverse `ticker_sequence` order first.
- No direct UPDATE or DELETE correction path exists.

Precise event definitions:

- A **normal event** is `buy`, `sell`, or `opening_balance`.
- A normal event is **effective** when no committed `reversal` row references its ID.
- A `reversal` is an immutable audit/effect event, but it is never itself a reversible normal event.
- The **latest effective transaction** is the effective normal event with the greatest `ticker_sequence` for the same owner, Portfolio, and ticker.
- An event is reversal-eligible only when it is that latest effective transaction and the current Holding quantity/average cost matches its stored after snapshot. Holding version may be newer because intervening reversal events consume sequence numbers.
- A reversal creates the next `ticker_sequence`, copies the current state as its before snapshot, and restores the target normal event's before quantity/average cost as its after snapshot.
- `portfolio_holdings.version` becomes the reversal's sequence. If the restored quantity is zero, the Holding row is removed, but the next reopen continues from `max(ticker_sequence) + 1` rather than resetting to 1.
- LIFO chain example: normal events `T1 buy`, `T2 buy`, `T3 sell` may be undone only as `R3 -> T3`, then `R2 -> T2`, then `R1 -> T1`. After `R3`, `T2` becomes the latest effective transaction even though `R3` has a higher sequence.
- A reversed normal Transaction is excluded from Decision fill totals. Reversal rows have `decision_id = null` and do not count as opposite-side fills.

## 6. Authentication, ownership, and RLS

### 6.1 Verified identity

All new `/portfolios` endpoints require `Authorization: Bearer <Supabase access token>`.

The API MUST verify:

- JWT signature against configured Supabase JWKS
- expected issuer
- expected audience
- expiration and not-before times
- `sub` is a valid UUID

Each verification is fail-closed and occurs before any database/RPC call. An invalid signature, invalid issuer, invalid audience, expired `exp`, invalid `nbf`, missing `sub`, or non-UUID `sub` returns `401 invalid_token` and performs no database read or mutation. A missing Bearer token remains the distinct `401 auth_required` case.

`owner_id` is the verified JWT `sub`, equivalent to Supabase `auth.uid()`.

The client MUST NOT provide `owner_id` in a path, query, or request body. Request models use `extra='forbid'`. An explicit `owner_id` field returns `422 owner_id_forbidden` and is never forwarded to the database.

### 6.2 New endpoint behavior

- Missing, expired, or invalid token: `401 auth_required` or `401 invalid_token`.
- Valid owner accessing their Portfolio: allowed by API and RLS.
- Valid owner requesting another owner's Portfolio: `404 portfolio_not_found`, not `403`, to avoid resource enumeration.
- Archived Portfolio: reads are allowed; new Transactions and Decisions return `409 portfolio_archived`.

### 6.3 RLS policies

RLS MUST be enabled on all Portfolio tables before any endpoint is exposed.

Policy rules:

```text
portfolios:
  SELECT TO authenticated: using owner_id = auth.uid()
  INSERT TO portfolio_rpc_owner: with check owner_id = auth.uid()
  UPDATE TO portfolio_rpc_owner: using/with check owner_id = auth.uid()
  DELETE: no policy

portfolio_holdings:
  SELECT TO authenticated: using owner_id = auth.uid()
  INSERT/UPDATE/DELETE TO portfolio_rpc_owner:
    using/with check owner_id = auth.uid()

portfolio_transactions:
  SELECT TO authenticated: using owner_id = auth.uid()
  INSERT TO portfolio_rpc_owner: with check owner_id = auth.uid()
  UPDATE/DELETE: no policy

investment_decisions:
  SELECT TO authenticated: using owner_id = auth.uid()
  INSERT/UPDATE TO portfolio_rpc_owner:
    using/with check owner_id = auth.uid()
  DELETE: no policy
```

Authenticated users receive direct `SELECT` privileges only. The dedicated RPC owner receives only the table privileges required by these policies. All mutations use reviewed RPC functions.

Mutation RPCs are `SECURITY DEFINER`, owned by a dedicated `NOLOGIN NOBYPASSRLS` role such as `portfolio_rpc_owner`, and set `search_path = pg_catalog`. Every `public` table/function and `auth.uid()` reference is schema-qualified. Portfolio tables use `FORCE ROW LEVEL SECURITY`; the RPC owner is not the table owner and remains subject to policies using `auth.uid()`. Execute is revoked from `public` and granted only to `authenticated`. RPCs do not accept `owner_id` input.

Portfolio creation uses an equivalent `create_portfolio(p_name, p_base_currency, p_timezone)` RPC. It writes `owner_id = auth.uid()` and cannot accept an owner override.

### 6.4 Service-role boundary

The current backend service-role store is for system market/ML data. New user Portfolio request paths MUST NOT use the service-role key.

Required implementation boundary:

- Portfolio API calls forward the verified user's Supabase access token and use the publishable/anon key.
- Portfolio functions live in a separate store module that requires a user access token.
- Generic service-role table helpers MUST NOT be used for Portfolio tables.
- Phase 1 application allowlists expose no Portfolio operation to background service-role jobs, and user request code must never instantiate a service-role Portfolio client. Supabase service-role bypass capability still exists at platform level and is treated as a credential-security boundary, not as an RLS guarantee.
- If a future maintenance job genuinely requires service-role Portfolio access, it needs a separately reviewed owner-scoped RPC, explicit owner parameter sourced from trusted job input, an allowlist of operations, and an audit record. No generic cross-owner scan/write is allowed by this contract.

### 6.5 Legacy `POST /portfolio`

The existing `POST /portfolio` remains an inline, stateless analysis endpoint:

- It continues accepting `PortfolioAnalysisRequest` with `holdings: list[HoldingRequest]`.
- It MUST NOT be changed to require or exclusively accept `portfolio_id`.
- It does not persist holdings or Transactions.
- Its current authentication behavior remains unchanged during Phase 1.
- It MUST NOT silently load authenticated Portfolio data.
- A future persisted analysis route, if needed, uses a distinct route such as `POST /portfolios/{portfolio_id}/analysis`.

## 7. Idempotency contract

### 7.1 Scope and canonical payload

Transaction idempotency is unique within `(owner_id, portfolio_id, idempotency_key)` and is enforced by a database unique constraint.

The server fingerprint includes normalized:

- transaction type
- ticker
- quantity and price at fixed decimal representation
- currency, fees, and fee currency
- trade date and execution timestamp
- decision ID only for the Phase 2 decision-aware request
- execution group ID
- correction group ID
- original transaction ID and reversal reason for a reversal request
- note after trim/null normalization

It excludes server-generated IDs/timestamps and `owner_id`. The database computes SHA-256 from canonical `jsonb` text after normalization.

### 7.2 Required behavior

- New key: create the Transaction and Holding projection once; return `201`, `idempotent_replay=false`.
- Same key and same fingerprint: return the original Transaction and its stored after-projection snapshot with `200`, `idempotent_replay=true`; do not update Holding again, even if later Transactions changed the current Holding.
- Same key and different fingerprint: return `409 idempotency_conflict`; do not mutate anything.
- Idempotency MUST use `INSERT ... ON CONFLICT` or equivalent unique-violation handling. A read-then-write uniqueness check is prohibited.
- Decision creation and reversal use the same scoped idempotency rules.

## 8. Atomic database operations

### 8.1 `record_portfolio_transaction` RPC

Proposed signature:

```sql
record_portfolio_transaction(
    p_portfolio_id uuid,
    p_idempotency_key uuid,
    p_transaction_type text,
    p_ticker text,
    p_quantity text,
    p_price text,
    p_currency text,
    p_fees text,
    p_fee_currency text,
    p_trade_date date,
    p_executed_at timestamptz,
    p_execution_group_id uuid default null,
    p_correction_group_id uuid default null,
    p_note text default null
) returns jsonb
```

This is the Phase 1 RPC and remains the standalone Transaction RPC after Phase 2. It never accepts a Decision ID and always writes `decision_id = null` after that nullable column exists.

Every PostgREST-exposed RPC name has exactly one signature. Function overloading is forbidden because PostgREST resolution can become ambiguous when optional/default arguments or schema cache versions differ.

`p_transaction_type` accepts only `buy`, `sell`, or `opening_balance`. Reversal uses a separate RPC. There is no `p_owner_id`.

Atomic algorithm:

1. Require non-null `auth.uid()`.
2. Select the owner-scoped Portfolio, regardless of active/archive status, and lock its row `FOR UPDATE`. This serializes first-version accounting writes within one Portfolio, including absent Holding rows.
3. Validate raw decimal text format, scale, precision, and sign before any cast; enforce all three USD invariants; normalize remaining input; then calculate the request fingerprint.
4. If archived, load only an existing row for the scoped idempotency key: return the stored result only when its fingerprint matches; otherwise reject `portfolio_archived`. This branch cannot create a row and therefore cannot race a new write.
5. If active, read the current Holding and `max(ticker_sequence)` under the already-held Portfolio lock; assign the next sequence without resetting after a closed/reopened position; compute before/after snapshots.
6. Reject over-sell, invalid opening balance, or mismatched Decision.
7. Attempt Transaction insert using the scoped unique key with `ON CONFLICT DO NOTHING RETURNING`.
8. If the insert conflicted, load the committed conflicting row, compare fingerprints, and return replay or conflict without changing Holding.
9. If inserted, upsert or delete the Holding projection and set Holding version to the inserted `ticker_sequence`.
10. Return Transaction and Holding output.

The RPC call is one PostgreSQL transaction. Any exception rolls back both event insertion and projection mutation.

Output:

```json
{
  "transaction": {
    "id": "uuid",
    "transaction_type": "sell",
    "position_effect": "decrease",
    "ticker": "NVDA",
    "quantity": "10.00000000",
    "price": "140.25000000",
    "trade_date": "2026-08-28",
    "executed_at": "2026-08-28T10:15:00+08:00"
  },
  "holding": {
    "ticker": "NVDA",
    "quantity": "15.00000000",
    "average_cost": "110.00000000",
    "cost_basis_total": "1650.00000000",
    "version": 4
  },
  "idempotent_replay": false
}
```

For a fully closed position, `holding` is `null`.

The response is assembled from the inserted Transaction's stored before/after snapshots. `ticker_sequence` is the original Holding version returned to the caller. An idempotent replay therefore returns the same original committed response rather than a later current Holding.

### 8.2 `reverse_portfolio_transaction` RPC

Proposed signature:

```sql
reverse_portfolio_transaction(
    p_portfolio_id uuid,
    p_transaction_id uuid,
    p_idempotency_key uuid,
    p_reason text,
    p_executed_at timestamptz,
    p_correction_group_id uuid default null
) returns jsonb
```

The function:

1. derives owner from `auth.uid()`;
2. locks the Portfolio row;
3. verifies the original scoped Transaction is the latest effective normal Transaction defined in Section 5.6 and that its after snapshot matches current projection state;
4. verifies it is not a reversal and has not already been reversed;
5. uses DB-unique idempotency handling;
6. inserts an immutable reversal event;
7. restores the original before snapshot in `portfolio_holdings`;
8. commits or rolls back the reversal and projection together.

### 8.3 `record_decision_transaction` RPC

Migration `018` introduces a separately named function; it does not overload `record_portfolio_transaction`:

```sql
record_decision_transaction(
    p_portfolio_id uuid,
    p_decision_id uuid,
    p_idempotency_key uuid,
    p_transaction_type text,
    p_ticker text,
    p_quantity text,
    p_price text,
    p_currency text,
    p_fees text,
    p_fee_currency text,
    p_trade_date date,
    p_executed_at timestamptz,
    p_execution_group_id uuid default null,
    p_correction_group_id uuid default null,
    p_note text default null
) returns jsonb
```

It applies the same decimal, USD, lock, idempotency, atomic projection, and error rules as the Phase 1 RPC, plus these checks under the same Portfolio lock:

- Decision belongs to `auth.uid()` and the requested Portfolio.
- Decision ticker equals normalized Transaction ticker.
- `buy` Decision accepts only `buy`; `reduce`/`exit` accept only `sell`.
- `hold` and `ignore_alert` reject every linked Transaction.
- Cancelled/expired Decisions reject new fills, while same-key/same-payload replays of previously committed fills remain readable.

### 8.4 RPC error behavior

RPCs raise stable application errors that the API maps without exposing SQL details:

| DB/application code | Condition | Mutation |
| --- | --- | --- |
| `auth_required` | `auth.uid()` is null | none |
| `portfolio_not_found` | scoped active/archived Portfolio is absent | none |
| `validation_error` | malformed domain input | none |
| `idempotency_conflict` | unique key exists with different fingerprint | none |
| `over_sell` | requested sell exceeds locked Holding | none |
| `opening_balance_conflict` | prior effective ticker event exists | none |
| `decision_mismatch` | Decision scope/ticker/action is incompatible | none |
| `reversal_not_latest` | original is not latest effective ticker event | none |
| `already_reversed` | reversal uniqueness conflict | none |
| unexpected exception | database/application fault | entire RPC transaction rolls back |

### 8.5 Concurrency and failure behavior

- All accounting writes for one Portfolio acquire the same Portfolio row lock before reading a Holding.
- Two concurrent sells are serialized. The second sees the first committed quantity and fails with `over_sell` if insufficient.
- A waiting duplicate idempotency request returns the first request's result after the unique conflict resolves.
- Deadlock/serialization retry MAY occur at the API layer a maximum of two times using the same idempotency key.
- Any exhausted database retry returns `503 persistence_unavailable`; the client may safely retry the same key.
- A database timeout or lost connection after the request reached PostgreSQL can leave the commit outcome unknown. The API MUST NOT infer rollback, generate a replacement idempotency key, or apply a separate Holding update. It returns `503 persistence_unavailable` and instructs the caller to retry the identical normalized request with the same key. If the original transaction committed, the retry returns its stored original result as an idempotent replay; the scoped DB unique constraint prevents a second Transaction and the replay path does not update the Holding. If the original transaction did not commit, the retry may create and project the Transaction exactly once.
- No response may claim success before the database transaction commits.

## 9. API contract

### 9.1 Common success envelope

```json
{
  "status": "success",
  "data": {},
  "error": null
}
```

### 9.2 Common error envelope

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "over_sell",
    "message": "Sell quantity exceeds the current holding.",
    "field": "quantity",
    "details": {}
  }
}
```

Production errors MUST NOT expose SQL, table names, service keys, stack traces, or another owner's resource existence.

### 9.3 Create Portfolio

`POST /portfolios`

Request:

```json
{
  "name": "Long-term Portfolio",
  "base_currency": "USD",
  "timezone": "Asia/Taipei"
}
```

`owner_id`, `id`, `status`, and timestamps are forbidden request fields.

`base_currency` may be omitted and defaults to `USD`. Any supplied value other than exact uppercase `USD` is rejected by both `create_portfolio` before insert and the `portfolios` DB CHECK.

Response: `201 Created`

```json
{
  "status": "success",
  "data": {
    "portfolio": {
      "id": "uuid",
      "name": "Long-term Portfolio",
      "base_currency": "USD",
      "timezone": "Asia/Taipei",
      "status": "active",
      "created_at": "2026-08-28T12:00:00Z"
    }
  },
  "error": null
}
```

The response does not need to expose `owner_id`; ownership comes from the authenticated session.

### 9.4 Phase 1 standalone Transaction request

`POST /portfolios/{portfolio_id}/transactions`

Request model: `PortfolioTransactionCreateV1`.

- Contains exactly the fields shown below.
- Uses `extra='forbid'`.
- Does not contain `owner_id` or `decision_id`.
- `quantity`, `price`, and `fees` are canonical decimal strings and are validated for format, precision, and scale before conversion.
- Calls only `record_portfolio_transaction`.

| Request field | API type | Required | Default / validation |
| --- | --- | --- | --- |
| `idempotency_key` | UUID string | yes | no default |
| `transaction_type` | literal string | yes | `buy`, `sell`, or `opening_balance` |
| `ticker` | string | yes | trim then uppercase ticker validation |
| `quantity` | canonical decimal string | yes | positive; precision 28, scale <= 8 before cast |
| `price` | canonical decimal string | yes | positive; precision 20, scale <= 8 before cast |
| `currency` | literal string | no | `USD`; every other value rejected |
| `fees` | canonical decimal string | no | `"0"`; nonnegative, precision 20, scale <= 8 before cast |
| `fee_currency` | literal string | no | `USD`; every other value rejected |
| `trade_date` | ISO date string | yes | not future in Portfolio timezone |
| `executed_at` | ISO timestamp with offset | yes | maximum five-minute future skew |
| `execution_group_id` | UUID string | no | null |
| `correction_group_id` | UUID string | no | null |
| `note` | string | no | null; trimmed, maximum 2,000 characters |

Request:

```json
{
  "idempotency_key": "09c4cc75-5d5c-4851-bf30-a83cef24f03c",
  "transaction_type": "sell",
  "ticker": "NVDA",
  "quantity": "10",
  "price": "140.25",
  "currency": "USD",
  "fees": "1.00",
  "fee_currency": "USD",
  "trade_date": "2026-08-28",
  "executed_at": "2026-08-28T10:15:00+08:00",
  "execution_group_id": "4e4dcdb0-9885-47f1-981a-f406f29cd9e3",
  "note": "Partial reduction"
}
```

Responses:

- `201`: new committed Transaction
- `200`: same-key/same-payload replay
- `409`: same-key/different-payload, over-sell, archived Portfolio, or opening-balance conflict
- `404`: Portfolio not found in the authenticated owner scope
- `422`: invalid field or owner field supplied

Sending `decision_id` to this route is always `422 extra_forbidden`, including after Phase 2. Decision-linked fills use a different route, request model, and RPC.

### 9.5 Opening-balance import

`POST /portfolios/{portfolio_id}/transactions` uses the same schema with:

```json
{
  "idempotency_key": "0054f08e-4267-4fef-8be1-e324b8855cca",
  "transaction_type": "opening_balance",
  "ticker": "VOO",
  "quantity": "12.50000000",
  "price": "410.25000000",
  "currency": "USD",
  "fees": "0",
  "fee_currency": "USD",
  "trade_date": "2026-08-28",
  "executed_at": "2026-08-28T00:00:00+08:00",
  "note": "Position balance imported as of this timestamp"
}
```

No separate direct Holding write endpoint exists. A later bulk import endpoint MAY be a convenience wrapper, but it must call the same atomic event logic for each position and define whole-batch atomicity separately.

### 9.6 Reverse/correct Transaction

`POST /portfolios/{portfolio_id}/transactions/{transaction_id}/reversal`

```json
{
  "idempotency_key": "d1cb65f3-f887-4571-b11f-ff44dd7a2301",
  "reason": "Incorrect quantity entered",
  "correction_group_id": "d43eec70-5719-4f1c-a854-31619397dc40",
  "executed_at": "2026-08-28T12:30:00+08:00"
}
```

The corrected replacement is submitted separately to the normal Transaction endpoint with a new idempotency key and the same correction group ID.

### 9.7 Create Decision

Reserved Phase 2 route: `POST /portfolios/{portfolio_id}/decisions`

```json
{
  "idempotency_key": "2f2c5703-e814-4be0-be06-79ee77c32e13",
  "ticker": "NVDA",
  "action": "reduce",
  "planned_quantity": "25",
  "reason": "Position concentration exceeds my limit",
  "thesis": "Long-term thesis remains intact",
  "risk_conditions": {
    "max_position_weight": "0.25"
  },
  "context_snapshot": {
    "data_as_of": "2026-08-28",
    "holding_quantity": "40"
  },
  "decided_at": "2026-08-28T09:00:00+08:00",
  "expires_at": null
}
```

`planned_quantity`, when present, is a canonical decimal string with the same pre-cast scale and precision checks as Transaction quantity.

### 9.8 Phase 2 Decision-linked Transaction request

`POST /portfolios/{portfolio_id}/decisions/{decision_id}/transactions`

Request model: `DecisionTransactionCreateV2`.

- `decision_id` comes only from the path and is forbidden in the body.
- The body uses the same execution fields as Phase 1 but permits only `buy` or `sell`, never `opening_balance`.
- It calls only `record_decision_transaction`.
- It validates Decision owner, Portfolio, ticker, action, and lifecycle under the same lock as the event/projection write.
- It shares the same Transaction idempotency unique constraint. Decision ID is included in its fingerprint.

Its body field table is identical to `PortfolioTransactionCreateV1` except:

- `transaction_type` permits only `buy` or `sell`;
- `opening_balance` is forbidden;
- the path requires `decision_id: UUID`;
- body fields `decision_id` and `owner_id` are forbidden;
- the request calls only `record_decision_transaction`.

```json
{
  "idempotency_key": "3eaabdb7-8c0d-417c-9ef5-0a9b8227923e",
  "transaction_type": "sell",
  "ticker": "NVDA",
  "quantity": "10.00000000",
  "price": "140.25000000",
  "currency": "USD",
  "fees": "1.00000000",
  "fee_currency": "USD",
  "trade_date": "2026-08-28",
  "executed_at": "2026-08-28T10:15:00+08:00",
  "execution_group_id": "4e4dcdb0-9885-47f1-981a-f406f29cd9e3",
  "note": "First partial fill"
}
```

Phase 1 MUST NOT define `DecisionTransactionCreateV2`, expose this route, or call this RPC. Migration `018` and Phase 2 introduce all three together.

### 9.9 Error mapping

| HTTP | Code | Required behavior |
| --- | --- | --- |
| `401` | `auth_required` | Bearer token missing |
| `401` | `invalid_token` | signature/issuer/audience/time validation failed |
| `404` | `portfolio_not_found` | missing or cross-owner Portfolio; same external response |
| `404` | `transaction_not_found` | missing scoped Transaction |
| `404` | `decision_not_found` | missing scoped Decision |
| `409` | `idempotency_conflict` | same key, different normalized fingerprint; no mutation |
| `409` | `over_sell` | quantity exceeds Holding; no mutation |
| `409` | `portfolio_archived` | accounting writes disabled |
| `409` | `opening_balance_conflict` | prior effective ticker history exists |
| `409` | `reversal_not_latest` | later effective ticker event exists |
| `409` | `already_reversed` | original already has a reversal |
| `422` | `validation_error` | invalid quantity, price, fee, currency, ticker, date, or timestamp |
| `422` | `owner_id_forbidden` | client attempted to set owner |
| `500` | `internal_error` | unexpected application failure; no internals exposed |
| `503` | `persistence_unavailable` | transient DB failure after bounded retry; same key is safe to retry |

### 9.10 Archive, restore, and hard-delete API

- `POST /portfolios/{portfolio_id}/archive` calls `archive_portfolio`; first transition returns `200`, and repeated archive is an idempotent `200`.
- `POST /portfolios/{portfolio_id}/restore` calls `restore_portfolio`; first transition returns `200`, and repeated restore is an idempotent `200`.
- Both routes derive owner from auth and return `404 portfolio_not_found` for missing/cross-owner IDs.
- Archive and restore mutate only `portfolios.status` and `updated_at`.
- No `DELETE /portfolios/{portfolio_id}` route exists in Phase 1 or Phase 2. A request receives `405 Method Not Allowed`.
- Direct database DELETE by `authenticated` is denied. The ownership FK also prevents silent `auth.users` deletion while Portfolio data remains.

## 10. Legacy regression contract

The following are release blockers:

- Existing `POST /portfolio` continues accepting inline `holdings` and returns its current analysis envelope.
- Existing `PortfolioAnalysisRequest` is not replaced by a persisted Portfolio request.
- Existing `HoldingRequest` is not reused as a Transaction request. Its optional `market_value`, `quantity`, and ambiguous `cost_basis` are analysis inputs, not accounting fields.
- Existing portfolio agent equal-weight fallback remains limited to stateless analysis and is never used to create accounting Holdings.
- Existing `POST /query` portfolio routing and `needs_holdings` behavior remain unchanged.
- Existing report, concentration, theme exposure, and risk-summary tests continue to pass.
- New authenticated routes use plural `/portfolios`; they do not shadow `/portfolio`.

Required legacy regression tests:

1. OpenAPI still contains `/portfolio` with `PortfolioAnalysisRequest`.
2. Inline holdings request still normalizes ticker and dispatches analysis.
3. `/portfolio` does not require `portfolio_id` or auth.
4. `/portfolio` does not write Portfolio tables.
5. `/query` without holdings still returns `needs_holdings` for portfolio intent.
6. `/query` with inline holdings still dispatches the legacy workflow.
7. Existing `tests/test_v5_portfolio.py` and `tests/test_api.py` remain green.

## 11. Migration plan and forward correction

No migration is created in Phase 0.

After contract approval, migration dependency is strict and linear:

```text
016 owner/auth + Portfolio/Holding foundation
    -> 017 immutable Transaction log + atomic Holding projection
        -> 018 Investment Decision + nullable Transaction relation
```

- `017` MUST NOT run unless `016` is recorded as successfully applied.
- `018` MUST NOT run unless `017` is recorded as successfully applied.
- A later migration MUST NOT be collapsed into or reordered ahead of its dependency after any environment has applied the earlier migration.

### Migration 016: owner/auth, Portfolios, and Holdings

Proposed `016_create_portfolio_owner_and_holdings.sql`:

1. create a dedicated `portfolio_rpc_owner` role with `NOLOGIN NOBYPASSRLS`;
2. establish the `auth.users(id)` ownership FK contract without modifying the `auth.users` table;
3. create `portfolios`, its owner-scoped unique key, indexes, and DB CHECK `base_currency = 'USD'`;
4. create `portfolio_holdings`, its composite primary key, quantity/cost/version checks, and owner/Portfolio FK;
5. stage `portfolio_holdings.last_transaction_id` as nullable and without an FK because `portfolio_transactions` does not exist yet;
6. enable and force RLS on `portfolios` and `portfolio_holdings` and create owner policies;
7. revoke direct mutations from `authenticated` and all access from `public`;
8. create/grant only the fixed-search-path `create_portfolio`, `archive_portfolio`, and `restore_portfolio` RPCs owned by `portfolio_rpc_owner`;
9. verify auth derivation, RLS, function ownership, grants, and cross-owner denial.

Migration `016` MUST NOT:

- create `portfolio_transactions`;
- create `investment_decisions`;
- create `record_portfolio_transaction` or reversal RPCs;
- create any FK from `portfolio_holdings` to a transaction table that does not yet exist;
- enable direct Holding writes.

No Holding row can be created through an exposed API after `016` alone. This guarantees that `last_transaction_id` can be tightened safely in `017`.

### Migration 017: immutable Transactions and atomic projection

Proposed `017_create_portfolio_transactions.sql`:

1. require all objects and grants from `016`;
2. create `portfolio_transactions` without a `decision_id` column;
3. add immutable-event validation, scoped keys, sequence checks, and query indexes;
4. add DB CHECK constraints `currency = 'USD'` and `fee_currency = 'USD'`; use text RPC parameters so scale/precision/sign are checked before numeric cast;
5. add DB-enforced `unique(owner_id, portfolio_id, idempotency_key)` and `unique(owner_id, portfolio_id, ticker, ticker_sequence)`;
6. add the scoped self-FK and partial unique index for `reversal_of_transaction_id`;
7. set a local five-second lock timeout, then acquire `LOCK TABLE public.portfolio_holdings IN ACCESS EXCLUSIVE MODE` inside the migration transaction before checking or tightening the staged column; timeout aborts the migration and leaves `016` unchanged;
8. while that lock is held, assert the table has zero rows; if the assertion fails, raise and roll back the entire migration rather than fabricate/backfill a Transaction ID;
9. while the same lock is held, add the scoped FK from `portfolio_holdings.last_transaction_id` to `portfolio_transactions` and change the column to `NOT NULL`;
10. create Transaction RLS/grants and the atomic RPC functions before commit, but do not enable the endpoint until the disposable-environment gate passes;
11. create/grant the uniquely named `record_portfolio_transaction` and `reverse_portfolio_transaction` functions;
12. verify pre-cast decimal rejection, USD invariants, insert + Holding projection update, idempotent replay, reversal chain, rollback, and concurrent sell behavior in one DB transaction.

Migration `017` MUST NOT:

- create `investment_decisions`;
- add `portfolio_transactions.decision_id`;
- create any FK to `investment_decisions`;
- accept a Decision identifier in its base Transaction RPC.

The Transaction endpoint remains disabled until both the `017` schema and atomic RPC verification pass.

The `017` deploy does not retry a failed/timeout tightening inside the same release. Operators first identify the unexpected writer/row, preserve evidence, and apply a reviewed forward remediation before rerunning the intact migration. No endpoint or direct authenticated Holding grant may be enabled between `016` and successful `017` completion.

### Migration 018: Investment Decisions and Transaction relation

Proposed `018_create_investment_decisions.sql`:

1. require `portfolio_transactions` and atomic RPCs from `017`;
2. create `investment_decisions`, field checks, scoped idempotency key, indexes, RLS, and grants;
3. create the Decision creation/lifecycle RPCs;
4. add nullable `portfolio_transactions.decision_id`;
5. add `(owner_id, portfolio_id, decision_id)` FK to `investment_decisions(owner_id, portfolio_id, id) on delete restrict`;
6. create the separately named `record_decision_transaction` RPC and validate owner, Portfolio, ticker, action, and lifecycle compatibility;
7. preserve `record_portfolio_transaction` unchanged for standalone Transactions; do not create any overloaded function name;
8. verify that existing Transactions remain valid with `decision_id = null`.

Migration `018` is the first migration allowed to add either the `decision_id` column or its FK. The column remains nullable because an actual Transaction may exist without a prior Decision.

### Future Alert migration boundary

The alert migration is `019` or later and is not part of the `016 -> 017 -> 018` approval chain. Proposed future `019_create_portfolio_alerts.sql`:

1. create owner-scoped alerts and RLS;
2. add `source_alert_id` to Decisions;
3. validate the composite FK;
4. do not grant Alerts any Transaction-writing capability.

### No destructive rollback

- Applied migrations are never rolled back by dropping Portfolio tables or deleting user records.
- If application deployment fails, disable the new routes and leave additive tables intact.
- If a schema defect is discovered, create the next numbered forward migration.
- Constraint corrections use add/backfill/validate/swap steps. Potentially failing constraints are added `NOT VALID` first, data is repaired, then constraints are validated.
- Column replacement uses add new column, deterministic backfill, dual-read/dual-write if needed, validation, application cutover, and only a later separately approved cleanup.
- RPC defects are corrected with `create or replace function` in a new migration while preserving one unambiguous signature per function name. New behavior requiring a different parameter set receives a new function name.
- Existing Transaction rows are never rewritten to hide a defect. Accounting corrections use reversal events; schema/data repair uses an audited forward migration.
- Before any route is enabled, migration and RLS verification must pass in a disposable Supabase/PostgreSQL environment.

## 12. Disposable Supabase security and grant integration gate

No Portfolio migration or endpoint may be promoted from Phase 1/2 development to a shared environment until this gate passes against a disposable Supabase project or local Supabase stack with Auth, PostgreSQL, and PostgREST versions matching the target environment.

Gate execution is required after `016`, again after `017`, and again after `018`. A later gate includes all earlier assertions.

### 12.1 Environment setup

1. Create a clean disposable Supabase database and apply existing migrations `001` through `015`.
2. Apply only the candidate migration prefix under test: `016`, then `016-017`, then `016-018`.
3. Create two verified Auth users, owner A and owner B, and obtain real signed access tokens for each.
4. Retain anon and service-role credentials only for negative/misuse tests; never print tokens in test output.
5. Exercise functions through PostgREST as well as direct PostgreSQL integration connections.
6. Destroy the disposable project/database after preserving sanitized test results.

### 12.2 Catalog and grant assertions

The gate MUST query PostgreSQL catalogs and assert:

- RLS is enabled and forced (`relrowsecurity=true`, `relforcerowsecurity=true`) on every Portfolio table present at that migration stage.
- `portfolio_rpc_owner` is `NOLOGIN` and `NOBYPASSRLS`, is not a member of `service_role`, and is not the owner of Portfolio tables.
- Every mutation function is `SECURITY DEFINER`, owned by `portfolio_rpc_owner`, uses fixed `search_path=pg_catalog`, and schema-qualifies every `public` and `auth` object reference.
- `public` and `anon` have no Portfolio table privileges and no execute privilege on Portfolio mutation functions.
- `authenticated` has only required SELECT and function EXECUTE grants; it has no direct INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, or TRIGGER privilege on Portfolio tables.
- `portfolio_rpc_owner` has only the minimum table privileges needed by approved functions and no ability to modify `auth.users`.
- Each PostgREST-exposed function name present at that migration prefix has exactly one `pg_proc` row/signature. After `017`, `record_portfolio_transaction` and `reverse_portfolio_transaction` are distinct and unique; after `018`, `record_decision_transaction` is also present as a third distinct name. None is an overload.
- PostgREST schema-cache reload resolves each RPC by name without ambiguity.

### 12.3 Auth/RLS behavior assertions

Using real owner A/B JWTs through PostgREST/API:

- owner A can create/read/archive/restore A's Portfolio;
- owner B cannot read or mutate A's Portfolio or child rows;
- cross-owner IDs produce the same external `404` as missing IDs;
- body/query owner spoofing is rejected before RPC invocation;
- direct table mutation as `authenticated` is denied even for the caller's own rows;
- approved RPC mutation succeeds only in the caller's scope;
- an archived Portfolio remains readable but rejects new accounting/Decision writes;
- direct hard delete and Auth-user cascading delete are denied;
- anon cannot read or mutate any Portfolio object.

The Supabase `service_role` is expected to bypass RLS at the platform level. The gate therefore also includes an application integration test that fails if any user Portfolio request constructs a service-role client or calls a generic service-role store helper. This contract does not claim RLS can constrain a leaked service-role credential.

### 12.4 Migration and atomicity assertions

- Applying `017` to a disposable `016` database containing a deliberately injected Holding row must block on/acquire the declared table lock and then fail the empty-table assertion; no `017` object may remain after rollback.
- Applying `017` to a clean `016` database must add the Holding FK and `NOT NULL` constraint in one migration transaction.
- Invalid 9-decimal or over-precision text passed directly to RPC must fail before cast and create no event.
- Direct SQL attempts to persist non-USD Portfolio/Transaction currency must fail DB CHECK constraints; RPC attempts must fail before insert.
- Forced Transaction insert/Holding update errors roll back the complete RPC transaction.
- Two independent sessions must demonstrate the concurrent-sell serialization rule.

Gate output records migration prefix, Supabase/PostgreSQL/PostgREST versions, passed assertion names, and sanitized failure details. Any failed assertion blocks endpoint enablement and migration promotion.

## 13. Test matrix

| Area | Case | Expected result |
| --- | --- | --- |
| Buy | First buy | one Transaction; Holding created; quantity and average cost include buy fee; effect `open` |
| Buy | Add to position | quantity increases; weighted average cost recalculated; effect `increase` |
| Sell | Partial sell | quantity decreases; average cost unchanged; effect `decrease` |
| Sell | Full sell | Holding row removed; Transaction retained; effect `close` |
| Fill | Partial execution | Decision 25, fills 10 and 5; Holding changes by 15; derived state `partially_executed` |
| Idempotency | Same key/same payload sequential | original result returned with replay true; one event/projection update |
| Idempotency | Same key/same payload concurrent | DB unique constraint admits one event; both callers observe same result |
| Idempotency | Same key/different payload | `409 idempotency_conflict`; no second mutation |
| Quantity | Zero quantity | `422 validation_error`; no event/projection mutation |
| Quantity | Negative quantity | `422 validation_error`; no mutation |
| Quantity | 9 fractional digits | API and direct RPC both reject before cast; no row written |
| Quantity | 9 digits with trailing zero | `1.123456780` still rejects; validation does not normalize away submitted scale |
| Quantity | Fractional share | accepted through 8 decimals; exact Decimal result |
| Quantity | 20 integer + 8 fractional digits | accepted when positive and within business constraints |
| Quantity | 21 integer digits | precision overflow rejected before cast |
| Price | Missing/null price | `422 validation_error`; no mutation |
| Price | Zero/negative price | `422 validation_error`; no mutation |
| Price | NaN/Infinity | `422 validation_error`; no mutation |
| Price | JSON number or exponent notation | rejected; only canonical decimal string accepted |
| Price | 9 fractional digits | API and direct RPC reject before cast; no silent numeric rounding |
| Fee | Negative fee | `422 validation_error` |
| Fee | 9 fractional digits | API and direct RPC reject before cast |
| Currency | Non-USD API/RPC request | `422 validation_error` before insert |
| Currency | Direct SQL non-USD Portfolio | DB CHECK rejects even with privileged test connection |
| Currency | Direct SQL non-USD trade/fee currency | DB CHECK rejects row |
| Date | Future trade date/timestamp | `422 validation_error` except allowed clock skew |
| Opening | Valid opening balance | opening event and Holding created; no fabricated lots |
| Opening | Prior effective history exists | `409 opening_balance_conflict` |
| Sell | Sell without Holding | `409 over_sell` |
| Sell | Sell above Holding | `409 over_sell`; Transaction insert and Holding update both absent |
| Decision | Planned action only | Decision exists; no Holding or Transaction change |
| Decision | Hold/ignore with quantity | `422 validation_error` |
| Decision | Transaction link mismatch | wrong owner/portfolio/ticker/action rejected with no mutation |
| Decision state | Hold/ignore | lifecycle remains independent; execution state `not_applicable` |
| Decision state | Buy/reduce with zero fills | execution state `planned` |
| Decision state | Fill below planned quantity | execution state `partially_executed` |
| Decision state | Fill equals planned quantity | execution state `executed` |
| Decision state | Fill exceeds planned quantity | execution state `over_executed`; original plan unchanged |
| Decision state | Exit-all closes Holding | final effective linked sell after snapshot zero -> `executed` |
| Decision state | Exit-all leaves Holding | effective linked sell after snapshot positive -> `partially_executed` |
| Decision state | Linked fill reversed | reversed fill excluded and execution state recomputed backward |
| Decision state | Cancelled after partial fill | lifecycle `cancelled`, execution state remains `partially_executed` |
| Request schema | Phase 1 body supplies decision ID | `422 extra_forbidden`; Phase 1 RPC not called |
| Request schema | Phase 2 Decision route | calls only `record_decision_transaction`; path Decision ID included in fingerprint |
| RPC resolution | PostgREST function catalog | exactly one signature per exposed name; no overload ambiguity/schema-cache error |
| Reversal | Reverse latest buy | reversal event appended; exact before projection restored |
| Reversal | Reverse latest sell | sold quantity and prior average cost restored |
| Reversal | Reverse non-latest event | `409 reversal_not_latest` |
| Reversal | Reverse twice | `409 already_reversed`; one reversal only by unique constraint |
| Reversal chain | Three normal events | must reverse T3, then T2, then T1; out-of-order request rejected |
| Reversal chain | Reverse T3 then evaluate T2 | T2 becomes latest effective normal despite reversal event having higher sequence |
| Reversal chain | Close, reopen, reverse | ticker sequence never resets; reversal eligibility remains deterministic |
| Reversal chain | Snapshot mismatch | reversal rejected and no row/projection mutation |
| Correction | Reversal plus replacement | two immutable events in correction group; final projection matches corrected input |
| Atomicity | Force Holding update failure | inserted Transaction rolls back; prior Holding unchanged |
| Atomicity | Force Transaction insert failure | Holding remains unchanged |
| Persistence retry | Commit succeeds but DB timeout/connection loss hides outcome | first API call returns `503 persistence_unavailable`; server does not claim rollback or retry with a new key |
| Persistence retry | Retry outcome-unknown request with same key and identical payload | returns the original committed result with replay true; exactly one Transaction exists; Holding quantity, average cost, last transaction, and version reflect exactly one update |
| Concurrency | Two valid concurrent sells | serialized; both commit only if total quantity is sufficient |
| Concurrency | Concurrent sells exceed quantity | first valid commit succeeds; second returns `409 over_sell`; quantity never negative |
| Auth | Missing/invalid JWT | `401`; no DB call or mutation |
| JWT claim | Invalid signature | `401 invalid_token`; no database/RPC call or mutation |
| JWT claim | Invalid issuer | `401 invalid_token`; no database/RPC call or mutation |
| JWT claim | Invalid audience | `401 invalid_token`; no database/RPC call or mutation |
| JWT claim | Expired `exp` | `401 invalid_token`; no database/RPC call or mutation |
| JWT claim | Invalid `nbf`, including a token not yet valid beyond allowed clock skew | `401 invalid_token`; no database/RPC call or mutation |
| JWT claim | Missing `sub` | `401 invalid_token`; no database/RPC call or mutation |
| JWT claim | Invalid/non-UUID `sub` | `401 invalid_token`; no database/RPC call or mutation |
| Auth | Body contains owner ID | `422 owner_id_forbidden`; supplied owner ignored |
| RLS | Owner reads own rows | allowed |
| RLS | Owner reads another owner's UUID | no rows / API `404` |
| RLS | Owner writes another owner's Portfolio | denied by RLS/RPC and externally reported as `404` |
| RLS | Child owner/Portfolio mismatch | composite FK rejects insert |
| Service role | Generic Portfolio access in request path | test fails if service-role store/helper is called |
| Grants | Authenticated direct DML | denied for own and cross-owner Portfolio tables |
| Grants | Public/anon privileges | no table access and no mutation-function execute privilege |
| Grants | RPC owner catalog properties | `NOLOGIN`, `NOBYPASSRLS`, not table owner, fixed `search_path=pg_catalog` |
| Migration 017 | Rogue Holding exists after 016 | ACCESS EXCLUSIVE lock acquired; empty-table assertion aborts and full migration rolls back |
| Migration 017 | Concurrent Holding writer | tightening waits for/fails lock according to timeout; never observes partially tightened schema |
| Migration 017 | Clean 016 database | FK plus NOT NULL added in one committed migration transaction |
| Archive | Archive with open Holding | only Portfolio status changes; Holding/history remain readable |
| Archive | New write while archived | `409 portfolio_archived`; no mutation |
| Archive | Same-key replay while archived | original committed response returned with `200`; no mutation |
| Archive | Restore then write | owner restores active state; subsequent new write may proceed |
| Hard delete | API delete attempt | `405`; route is absent |
| Hard delete | Direct authenticated DELETE | grant/RLS denial, including empty Portfolio |
| Hard delete | Delete Auth user with Portfolio | ownership FK restricts silent cascade |
| Legacy | `POST /portfolio` inline request | current success shape and analysis behavior preserved |
| Legacy | `/portfolio` without auth | current behavior preserved |
| Legacy | `/portfolio` does not persist | Portfolio store mocks receive no call |
| Legacy | `/query` portfolio routing | `needs_holdings` and inline dispatch remain unchanged |
| Regression | Existing portfolio/API suite | all current tests pass unchanged |

Test layers required before Phase 1 approval:

- Pydantic/API schema unit tests
- Decimal accounting unit tests
- RPC integration tests against disposable PostgreSQL/Supabase
- concurrency tests using two independent DB connections
- RLS tests using two authenticated test users plus a service-role misuse guard
- existing API/portfolio regression tests

## 14. Acceptance criteria for Phase 0

Phase 0 is ready for Reviewer/QA only when the reviewer can answer yes to all of the following:

- Holding, Transaction, Decision, and Alert semantics cannot be confused.
- Every proposed field has type, nullability, default, precision, validation, uniqueness, and FK behavior.
- Owner identity comes only from a verified auth token and `auth.uid()`.
- Direct client owner assignment and cross-owner access are prohibited.
- Transaction insertion and Holding projection update are one atomic DB transaction.
- Idempotency relies on a scoped DB unique constraint, not read-then-write.
- Partial fills, over-sell, opening balance, reversal, and correction have deterministic behavior.
- Latest effective event, LIFO reversal chain, and two-dimensional Decision state are deterministic.
- Decimal scale/precision is rejected before cast/write, and USD-only is enforced by both RPC and DB CHECK.
- Phase 1 and Phase 2 use separate request models, routes, and uniquely named RPCs with no PostgREST overload.
- `017` nullable tightening uses a bounded ACCESS EXCLUSIVE lock and fails closed.
- Archive preserves all records and hard delete is unavailable.
- The disposable Supabase security/grant gate is mandatory and fully specified.
- A simulated committed-but-response-lost persistence failure returns `503`, then a same-key retry proves that only the original Transaction and one Holding projection update exist.
- JWT negative tests independently prove fail-closed handling for signature, issuer, audience, `exp`, `nbf`, and missing/invalid `sub`, with no database/RPC call.
- Existing `POST /portfolio` remains backward compatible.
- Rollback does not destroy committed user data.
- The test matrix covers domain, concurrency, RLS, failure rollback, and legacy regression.

## 15. Fixed decisions and future review boundary

This contract fixes the following first-version choices; none remains an implementation-time choice:

- cost basis method: moving average, not tax lots;
- buy fees are included in average cost; sell fees do not change remaining average cost;
- currency: USD only, including fee currency;
- correction: only the latest effective normal ticker Transaction may be reversed in LIFO sequence order;
- write serialization: Portfolio-level row lock for correctness before later optimization;
- ownership: verified Supabase user JWT, user-token database calls, RLS, no service-role request path;
- hard deletion: no API or authenticated direct-delete path, including an empty Portfolio;
- decimal input: canonical strings, maximum scale 8 checked before cast, no silent input rounding;
- RPC naming: one unique signature per exposed function name, with a distinct Decision-linked function;
- archive: read-only until explicitly restored.

Non-blocking future product decisions include multi-currency support, a higher-throughput lock strategy, corporate actions, tax lots, and account-erasure retention workflow. Each requires a later reviewed contract and forward migration; none may be improvised during Phase 1.
