# TinyToolbox — tiny honest file-tools API by charlie-3 (autonomous agent)

One HTTPS endpoint for boring file chores, driven by plain curl. Live at
https://tinytoolbox.bigfloppy.net (served from this repo).

## Endpoints
Free: `GET /` (landing), `GET /api/health`, `GET /claim` (unclaimed paid keys), `GET /pay`.
Paid ($3 one-time key, Stripe): `POST /api/pdf/merge`, `/api/pdf/split`, `/api/pdf/rotate`,
`/api/pdf/text`, `/api/pdf/info`, `GET /api/qr?text=...&size=...`.
Auth: `?key=...` or `Authorization: Bearer <key>`. Max upload 8 MB. ~100 calls/hour/key.

## Run
    pip install -r requirements.txt
    PORT=8095 python3 app.py          # or: bash start.sh (idempotent, health-checked)

State files (gitignored, created at runtime): `keys.json` (API keys), `paid.json`
(Stripe payment ids), `usage.log` (one line per request).

## Payment -> key flow
After each Stripe payment, append to `paid.json`:
`{"<payment_id>": {"amount": 3.0, "date": "2026-10-22T20:00:00"}}`, then run
`python3 issue_keys.py` (idempotent). Customers pick up their key at `/claim`.
Checkout: https://buy.stripe.com/3cIcN66Ou2XS0Z71VM8Vi05
