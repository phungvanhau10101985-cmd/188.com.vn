# Parity reconcile rollout

The SQL migrations are schema-only. Run the reconciler without flags and
review its counts before explicit `--apply`. Apply runs in one transaction and
creates unique indexes only after deterministic reconciliation succeeds.

## Local (Windows PowerShell)

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/database_migrations/004_parity_hardening.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/database_migrations/005_schema_audit_parity.sql
Set-Location backend
python scripts/reconcile_order_schema_parity.py
python scripts/reconcile_order_schema_parity.py --apply
python scripts/reconcile_order_schema_parity.py
```

Review the first report before running `--apply`. The final report must show
zero warehouse mismatches and duplicate rows.

## VPS

```bash
cd /var/www/188.com.vn
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/database_migrations/004_parity_hardening.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/database_migrations/005_schema_audit_parity.sql
cd backend
python scripts/reconcile_order_schema_parity.py
python scripts/reconcile_order_schema_parity.py --apply
python scripts/reconcile_order_schema_parity.py
```

Duplicate SePay payments, customer reviews (including useful-vote snapshots),
and notifications are copied to `parity_reconcile_archive` before the active
row is nulled or removed. Legacy active warehouse holds are converted to the
additive reservation model only inside the same explicit apply transaction.
