import math
import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_from_directory

DB_PATH = os.environ.get("DB_PATH", "dosimeter.db")
API_KEY = os.environ.get("API_KEY", "change-me")
# Kalibrace: kolik µSv/h odpovídá 1 cpm gama. 0 = dávka se nezobrazuje.
CPM_TO_USVH = float(os.environ.get("CPM_TO_USVH", "0"))

app = Flask(__name__, static_folder="static")


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


with db() as con:
    con.execute(
        """CREATE TABLE IF NOT EXISTS measurements(
        id INTEGER PRIMARY KEY, device_id TEXT NOT NULL, ts TEXT NOT NULL,
        t_open REAL NOT NULL, n_open INTEGER NOT NULL,
        t_shield REAL NOT NULL, n_shield INTEGER NOT NULL)"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_ts ON measurements(ts)")


def enrich(r):
    """Z počtů impulzů spočítá gama, beta, nejistotu a typ záření."""
    cpm_open = r["n_open"] / r["t_open"] * 60      # beta + gama
    cpm_shield = r["n_shield"] / r["t_shield"] * 60  # jen gama (beta stíní clona)
    beta = max(0.0, cpm_open - cpm_shield)
    sigma = 60 * math.sqrt(r["n_open"] / r["t_open"] ** 2 + r["n_shield"] / r["t_shield"] ** 2)
    return {
        "id": r["id"], "device_id": r["device_id"], "ts": r["ts"],
        "duration_s": r["t_open"] + r["t_shield"],
        "total_cpm": round(cpm_open, 2), "gamma_cpm": round(cpm_shield, 2),
        "beta_cpm": round(beta, 2), "sigma_cpm": round(sigma, 2),
        "beta_share": round(beta / cpm_open, 3) if cpm_open else 0,
        # beta považujeme za prokázanou, jen pokud přesahuje 2 sigma
        "type": "beta+gamma" if beta > 2 * sigma else "gamma",
        "dose_usvh": round(cpm_shield * CPM_TO_USVH, 3) if CPM_TO_USVH > 0 else None,
    }


@app.post("/api/measurements")
def add():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify(error="Neplatný API klíč"), 401
    d = request.get_json(silent=True) or {}
    try:
        t_open, t_shield = float(d["t_open"]), float(d["t_shield"])
        n_open, n_shield = int(d["n_open"]), int(d["n_shield"])
        if min(t_open, t_shield) <= 0 or min(n_open, n_shield) < 0:
            raise ValueError
        if d.get("ts"):
            ts = datetime.fromisoformat(d["ts"].replace("Z", "+00:00"))
            ts = ts.astimezone(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Očekávám t_open, n_open, t_shield, n_shield (kladné) a volitelně ts (ISO 8601)"), 400
    with db() as con:
        con.execute(
            "INSERT INTO measurements(device_id,ts,t_open,n_open,t_shield,n_shield) VALUES(?,?,?,?,?,?)",
            (str(d.get("device_id", "dozimetr-1")), ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
             t_open, n_open, t_shield, n_shield),
        )
    return jsonify(ok=True), 201


@app.get("/api/measurements")
def list_():
    q, args = "SELECT * FROM measurements WHERE 1=1", []
    if request.args.get("from"):
        q += " AND ts >= ?"; args.append(request.args["from"])
    if request.args.get("to"):
        q += " AND ts <= ?"; args.append(request.args["to"] + "T23:59:59Z")
    if request.args.get("device"):
        q += " AND device_id = ?"; args.append(request.args["device"])
    q += " ORDER BY ts DESC LIMIT ?"
    args.append(min(int(request.args.get("limit", 500)), 5000))
    with db() as con:
        return jsonify([enrich(r) for r in con.execute(q, args)])


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)