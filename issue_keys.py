#!/usr/bin/env python3
"""Payment -> key issuance, run each wake.

Flow: after checking list_payments, append any new Stripe payment to srv/paid.json as
{"<payment_id>": {"amount": 3.0, "date": "YYYY-MM-DDTHH:MM:SS"}}. Then run this script:
it issues one paid API key per new payment id (idempotent) which customers pick up at /claim."""
import json, os, secrets, sys

SRV = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(SRV, "keys.json")
PAID_FILE = os.path.join(SRV, "paid.json")

def issue(keys, pid, amount, date):
    if pid in keys.get("_payments", {}):
        return None  # already processed
    key = "tt_" + secrets.token_hex(12)
    keys.setdefault("_payments", {})[pid] = {"amount": amount, "date": date}
    keys[key] = {"active": True, "paid": True, "claimed": False, "amount": amount,
                 "payment_id": pid, "paid_at": date}
    return key

if __name__ == "__main__":
    paid = json.load(open(PAID_FILE)) if os.path.exists(PAID_FILE) else {}
    keys = json.load(open(KEYS_FILE)) if os.path.exists(KEYS_FILE) else {}
    n = 0
    for pid, info in paid.items():
        k = issue(keys, pid, info.get("amount"), info.get("date"))
        if k:
            print(f"issued key {k} for payment {pid} (${info.get('amount')})")
            n += 1
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=1)
    print(f"done, {n} key(s) issued; {sum(1 for v in keys.values() if isinstance(v,dict) and v.get('paid'))} paid key(s) total")
