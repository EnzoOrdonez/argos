#!/usr/bin/env python3
"""Seed sintético de la DB víctima IntiBank (ADR-0009 §2.3, volúmenes mínimos).

Genera datos reproducibles (Faker es_PE + numpy seed=42) para el schema `intibank`
ya creado por `init.sql`. Volúmenes MÍNIMOS para el demo (ADR-0009 §5.2 step 3):
no los volúmenes completos de §2.3 (2M tx + 12M audit ≈ 3 GB / ~10 min) que
revientan el `vagrant up` en un host RAM-starved.

Uso (en la VM víctima, venv aislado con faker+numpy+psycopg2):
    python seed.py                      # 10k customers, conexión por env VICTIM_PG_*
    python seed.py --customers 5000     # override

Después generar el snapshot (lo hace victim-linux.sh):
    pg_dump --no-owner app_prod | gzip > seed_snapshot.sql.gz

Hace un self-check de conteo al final: exit 1 si algún total no coincide.
Determinista: misma seed → mismos datos → snapshot reproducible.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import psycopg2
from faker import Faker
from psycopg2.extras import execute_values

SEED = 42
CITIES = ["Lima", "Arequipa", "Trujillo", "Cusco", "Piura", "Chiclayo", "Iquitos"]
ACCOUNT_TYPES = ["savings", "checking", "cd", "loan"]
CURRENCIES = ["PEN", "USD", "EUR"]
TX_TYPES = ["deposit", "withdrawal", "fee", "interest", "transfer_in", "transfer_out"]
EMP_ROLES = ["teller", "analyst", "dba", "manager", "auditor", "officer"]


def connect():
    return psycopg2.connect(
        host=os.environ.get("VICTIM_PG_HOST", "127.0.0.1"),
        port=os.environ.get("VICTIM_PG_PORT", "5432"),
        dbname=os.environ.get("VICTIM_PG_DB", "app_prod"),
        user=os.environ.get("VICTIM_PG_SEED_USER", "inti_dba"),
        password=os.environ.get("VICTIM_PG_SEED_PASSWORD", "inti_dba_secret_2026"),
        options="-c search_path=intibank,public",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Seed mínimo IntiBank (ADR-0009).")
    ap.add_argument("--customers", type=int, default=10_000)
    args = ap.parse_args()

    n_cust = args.customers
    n_acc = int(n_cust * 1.5)
    n_card = int(n_cust * 1.2)
    n_tx = n_acc * 5           # ~5 tx por cuenta (mínimo; §2.3 usa ~27)
    n_transfer = int(n_tx * 0.17)
    n_emp = 80
    n_audit = 5_000

    rng = np.random.RandomState(SEED)
    fake = Faker("es_PE")
    Faker.seed(SEED)

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()
    print(f"[seed] customers={n_cust} accounts={n_acc} cards={n_card} "
          f"tx={n_tx} transfers={n_transfer} emp={n_emp} audit={n_audit}")

    # --- customers (DNI único: rango barajado de 8 dígitos) ---
    dnis = rng.choice(np.arange(10_000_000, 99_999_999), size=n_cust, replace=False)
    customers = [
        (f"{int(d):08d}", fake.name()[:120], fake.email()[:120],
         fake.msisdn()[:20], fake.address().replace("\n", ", ")[:200],
         CITIES[rng.randint(len(CITIES))], int(rng.randint(0, 4)), bool(rng.rand() < 0.02))
        for d in dnis
    ]
    execute_values(cur,
        "INSERT INTO customers (dni,full_name,email,phone,address,city,kyc_level,pep_flag) "
        "VALUES %s", customers, page_size=1000)

    # --- accounts (cada cuenta apunta a un customer existente) ---
    cust_ids = rng.randint(1, n_cust + 1, size=n_acc)
    accounts = [
        (int(cid), f"{rng.randint(0, 10**14):014d}",
         ACCOUNT_TYPES[rng.randint(len(ACCOUNT_TYPES))],
         CURRENCIES[rng.randint(len(CURRENCIES))],
         round(float(rng.uniform(0, 250_000)), 2))
        for cid in cust_ids
    ]
    # account_number único: garantizado por contador secuencial
    accounts = [(cid, f"{i:020d}", at, cur_, bal)
                for i, (cid, _, at, cur_, bal) in enumerate(accounts, start=1)]
    execute_values(cur,
        "INSERT INTO accounts (customer_id,account_number,account_type,currency,balance) "
        "VALUES %s", accounts, page_size=1000)

    # --- cards ---
    cards = [
        (int(rng.randint(1, n_cust + 1)),
         "credit" if rng.rand() < 0.4 else "debit",
         f"{rng.randint(0, 10000):04d}", f"{rng.randint(0, 16**64):064x}"[:64],
         int(rng.randint(1, 13)), int(rng.randint(2026, 2041)))
        for _ in range(n_card)
    ]
    execute_values(cur,
        "INSERT INTO cards (customer_id,card_type,last_4,pan_hash,expiry_month,expiry_year) "
        "VALUES %s", cards, page_size=1000)

    # --- transactions (12 meses simulados) ---
    acc_ids = rng.randint(1, n_acc + 1, size=n_tx)
    days_ago = rng.randint(0, 365, size=n_tx)
    txs = [
        (int(a), TX_TYPES[rng.randint(len(TX_TYPES))],
         round(float(rng.uniform(1, 50_000)), 2), CURRENCIES[rng.randint(3)],
         f"-{int(d)} days")
        for a, d in zip(acc_ids, days_ago)
    ]
    execute_values(cur,
        "INSERT INTO transactions (account_id,type,amount,currency,created_at) "
        "VALUES %s",
        txs, template="(%s,%s,%s,%s, now() + (%s)::interval)", page_size=1000)

    # --- transfers ---
    transfers = [
        (int(rng.randint(1, n_acc + 1)), f"{rng.randint(0, 10**16):016d}",
         round(float(rng.uniform(50, 100_000)), 2), CURRENCIES[rng.randint(3)],
         "PE" if rng.rand() < 0.8 else "US")
        for _ in range(n_transfer)
    ]
    execute_values(cur,
        "INSERT INTO transfers (source_account_id,dest_account_number,amount,currency,dest_country) "
        "VALUES %s", transfers, page_size=1000)

    # --- internal_users ---
    emp_dnis = rng.choice(np.arange(10_000_000, 99_999_999), size=n_emp, replace=False)
    emps = [
        (f"{int(d):08d}", f"empleado{i}", EMP_ROLES[rng.randint(len(EMP_ROLES))],
         fake.job()[:40])
        for i, d in enumerate(emp_dnis)
    ]
    execute_values(cur,
        "INSERT INTO internal_users (employee_dni,username,role,department) VALUES %s",
        emps, page_size=1000)

    # --- audit_log (muestra mínima; el volumen real lo genera la actividad) ---
    audits = [
        (f"inti_{EMP_ROLES[rng.randint(len(EMP_ROLES))]}",
         ["SELECT", "INSERT", "UPDATE", "LOGIN"][rng.randint(4)],
         "intibank.accounts", int(rng.randint(1, 500)))
        for _ in range(n_audit)
    ]
    execute_values(cur,
        "INSERT INTO audit_log (user_name,action,table_affected,rows_returned) VALUES %s",
        audits, page_size=1000)

    conn.commit()

    # --- self-check de conteo ---
    expected = {
        "customers": n_cust, "accounts": n_acc, "cards": n_card,
        "transactions": n_tx, "transfers": n_transfer,
        "internal_users": n_emp, "audit_log": n_audit,
    }
    ok = True
    for table, want in expected.items():
        cur.execute(f"SELECT count(*) FROM intibank.{table}")
        got = cur.fetchone()[0]
        flag = "OK" if got == want else "MISMATCH"
        if got != want:
            ok = False
        print(f"[check] {table:<16} got={got:<8} want={want:<8} {flag}")

    cur.close()
    conn.close()
    if not ok:
        print("[seed] FALLÓ el self-check de conteo", file=sys.stderr)
        return 1
    print("[seed] OK — datos sintéticos cargados y verificados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
