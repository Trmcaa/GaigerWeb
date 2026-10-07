# Dozimetr β/γ – webová část

Server (Flask + SQLite) přijímá měření ze zařízení a zobrazuje je v dashboardu: datum, délka, typ záření (gama / beta + gama), graf v čase, export CSV.

## Spuštění

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
API_KEY=moje-tajne-heslo CPM_TO_USVH=0 python server.py
# dashboard: http://localhost:8000
```

Na serveru: `gunicorn -w 2 -b 0.0.0.0:8000 server:app` (za HTTPS reverzní proxy, např. Caddy nebo nginx).

| Proměnná | Význam |
|---|---|
| `API_KEY` | klíč, který musí zařízení poslat v hlavičce `X-API-Key` |
| `CPM_TO_USVH` | kalibrační faktor µSv/h na 1 cpm gama (0 = dávka se nezobrazuje) |
| `DB_PATH` | cesta k SQLite souboru |

## Jak se počítá beta a gama

Zařízení měří dva cykly: **bez clony** (beta + gama) a **s clonou** (jen gama).

- gama = impulzy s clonou / čas
- beta = max(0, bez clony − s clonou)
- nejistota σ = √(N₁/t₁² + N₂/t₂²) (Poisson)
- beta se označí za prokázanou, jen když je větší než 2σ

## API pro zařízení

```bash
curl -X POST http://localhost:8000/api/measurements \
  -H "Content-Type: application/json" -H "X-API-Key: moje-tajne-heslo" \
  -d '{"device_id":"dozimetr-1","ts":"2026-10-07T12:00:00Z",
       "t_open":60,"n_open":42,"t_shield":60,"n_shield":31}'
```

`ts` je volitelné (jinak se použije čas serveru). `GET /api/measurements?from=2026-10-01&to=2026-10-07` vrací měření jako JSON.

## Poznámka

Dávka v µSv/h je jen tak přesná, jak přesná je kalibrace trubice vůči referenčnímu zdroji. Dokud kalibraci nemáš, nech `CPM_TO_USVH=0` a pracuj s cpm.