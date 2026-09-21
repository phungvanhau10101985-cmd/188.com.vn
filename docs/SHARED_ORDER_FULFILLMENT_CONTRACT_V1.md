# Shared Order Fulfillment Contract v1

Version: **1.2.0**
Golden fixture: `contracts/shared-order-fulfillment-v1.json`

This is the cross-repository behavioral boundary for NanoAI and 188. The JSON fixture is normative; this document is its concise reading guide. Runtime orchestration remains repository-owned.

## Required behavior

- **Checkout:** classify by trusted source host, split a mixed cart into stable VN then CN orders under one checkout group, commit atomically, allocate discount proportionally, and charge shipping once (VN first). A percentage deposit is calculated from the discounted merchandise amount, excluding shipping.
- **Deposit SLA:** issue idempotent reminders at 2h and 20h. At 24h, release reserved VN warehouse stock once. Do not release CN stock and do not auto-cancel either order.
- **SePay:** `transaction_id` is the replay key. The first valid delivery applies payment and downstream effects once; an identical replay returns success as an acknowledged duplicate with no mutation or repeated notification/grant.
- **CN shipment:** automatic and EMS milestones stop at `at_customs`. Only an explicit authorized customs-clear action may advance it. Customer receipt confirmation is unavailable before `awaiting_confirm` is active.
- **Delivered:** set `delivered_at` once, complete the timeline, deduct reserved VN warehouse stock once, confirm affiliate commission once, and send delivery/review effects once.
- **Returned:** EMS must report the return and the shop must confirm receipt. Then set `returned_at` once, skip remaining timeline steps, restore VN warehouse stock once, cancel affiliate commission once, and do not refund affiliate wallet usage. Replays are no-ops.
- **Concurrency and rollback:** reservation locks the SKU row, admits only available stock, and a failed VN/CN checkout rolls back every order, reservation, notification, and affiliate effect.
- **COD and late deposit:** COD reserves VN warehouse stock at checkout. A deposit arriving after the 24h release must recheck stock and enter manual resolution instead of silently confirming.
- **Replay and affiliate lifecycle:** EMS and SePay replay keys are idempotent. Affiliate commission is granted once after deposit (or immediately for no-deposit orders), confirmed once on delivery, cancelled once on return, and wallet usage is not refunded by a return.

## Executable parity gate

Run `python tools/order_fulfillment_parity.py --self-test`. Add
`--peer-fixture ../other-repo/contracts/shared-order-fulfillment-v1.json` to enforce byte identity, or
`--baseline old.json --candidate optimized.json --write-sanitized artifacts/parity` to compare sanitized shadow snapshots.

Integration/E2E mode runs commands that must print JSON:

```text
FULFILLMENT_PARITY_REQUIRE_INTEGRATION=1
FULFILLMENT_PARITY_BASELINE_CMD=<baseline snapshot command>
FULFILLMENT_PARITY_CANDIDATE_CMD=<candidate snapshot command>
python tools/order_fulfillment_parity.py --integration --tenant-id <tenant>
```

Each command must return `{"scenarios":[{"scenario_id":"checkout_vn_cn_split", ...}, ...]}` covering all golden IDs.
When integration is required, missing commands, missing scenarios, non-zero commands, invalid JSON, or a semantic diff fail closed.

## Tenant rollout flag

- `ORDER_FULFILLMENT_OPTIMIZED_MODE=off|shadow|enforce` defaults to `off`.
- `ORDER_FULFILLMENT_OPTIMIZED_TENANTS='{"tenant-id":"shadow"}'` overrides per tenant.
- `enforce` remains effectively `off` unless `ORDER_FULFILLMENT_PARITY_GATE_PASSED=1`.
- `shadow` compares behavior only; it must not own mutations or side effects.

## Compatibility and changes

- Consumers must reject an unsupported `fixture_schema_version`.
- Additive optional fields may be introduced in a minor contract version.
- Changed money allocation, transition order, idempotency, or side effects require a new fixture and contract version in both repositories.
- Both fixture files must remain byte-for-byte identical.

## Rollout runbook

1. Keep `ORDER_FULFILLMENT_OPTIMIZED_MODE` unset (or `off`) by default.
2. Run `npm run test:fulfillment-parity:golden` and
   `npm run test:fulfillment-parity:integration` in NanoAI; run the same commands
   from `188-com-vn/frontend`. The deterministic integration gate needs no DB and
   compares all 15 fixture scenarios across the two repositories.
3. Enable `shadow` for selected tenant IDs. The legacy result remains authoritative;
   mismatch logs contain only tenant/result hashes and operation metadata.
4. For live integration, explicitly set `ORDER_FULFILLMENT_PARITY_LIVE=1`,
   `ORDER_FULFILLMENT_PARITY_TENANT_ID`, `FULFILLMENT_PARITY_BASELINE_CMD`, and
   `FULFILLMENT_PARITY_CANDIDATE_CMD`, then run
   `npm run test:fulfillment-parity:integration:live`. Snapshot commands need a
   configured DB/services tenant and must emit all 15 `scenario_id` rows.
5. Set `ORDER_FULFILLMENT_PARITY_GATE_PASSED=1` only after golden, deterministic,
   and required live gates pass. `enforce` otherwise fails closed to `off`.
6. Roll back immediately by setting the mode to `off`; no schema rollback is needed.
