import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .rota import candidates, compute_stats, ranking

# ---------- configurare ----------
MEMBERS = [
    m.strip()
    for m in os.getenv("MEMBERS", "Razvan,Andrei,Vlad,Alex,Dragos,Zsolt").split(",")
    if m.strip()
]
PIN = os.getenv("GROUP_PIN", "")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "rota.db"
STATIC_DIR = Path(__file__).parent / "static"

if not PIN:
    raise RuntimeError("Variabila GROUP_PIN lipsește (setează-o în .env).")

DATA_DIR.mkdir(parents=True, exist_ok=True)
_secret_file = DATA_DIR / "secret.key"
if not _secret_file.exists():
    _secret_file.write_text(secrets.token_hex(32))
SECRET = _secret_file.read_text().strip()

# ---------- baza de date ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS outings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    restaurant TEXT NOT NULL,
    attendees TEXT NOT NULL,
    payer TEXT NOT NULL,
    draw TEXT,
    manual INTEGER NOT NULL DEFAULT 0,
    entered_by TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);
"""


def _connect():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


with _connect() as _c:
    _c.execute("PRAGMA journal_mode=WAL")
    _c.executescript(SCHEMA)


@contextmanager
def tx(write=False):
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def _row(r):
    return {
        "id": r["id"],
        "date": r["date"],
        "restaurant": r["restaurant"],
        "attendees": json.loads(r["attendees"]),
        "payer": r["payer"],
        "draw": json.loads(r["draw"]) if r["draw"] else None,
        "manual": bool(r["manual"]),
        "entered_by": r["entered_by"],
    }


def load_outings(conn):
    rows = conn.execute(
        "SELECT * FROM outings WHERE deleted_at IS NULL ORDER BY date, id"
    ).fetchall()
    return [_row(r) for r in rows]


# ---------- autentificare (PIN comun) ----------
def _token():
    return hmac.new(SECRET.encode(), PIN.encode(), hashlib.sha256).hexdigest()


def require_auth(request: Request):
    cookie = request.cookies.get("rota_auth", "")
    if not hmac.compare_digest(cookie, _token()):
        raise HTTPException(401, "Neautentificat")


_fails: dict[str, list[float]] = {}


def _check_rate(ip: str):
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 600]
    _fails[ip] = recent
    if len(recent) >= 10:
        raise HTTPException(429, "Prea multe încercări. Mai încearcă peste câteva minute.")


app = FastAPI(title="Cine plătește?", docs_url=None, redoc_url=None, openapi_url=None)


class LoginIn(BaseModel):
    pin: str


class PresentIn(BaseModel):
    present: list[str]


class OutingIn(BaseModel):
    day: str
    restaurant: str
    present: list[str]
    payer: str | None = None
    entered_by: str | None = None


def _validate_present(present: list[str]):
    if len(set(present)) != len(present):
        raise HTTPException(400, "Nume duplicate în lista celor prezenți.")
    if any(p not in MEMBERS for p in present):
        raise HTTPException(400, "Nume necunoscut în lista celor prezenți.")
    if len(present) < 2:
        raise HTTPException(400, "Trebuie să fie prezente cel puțin 2 persoane.")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/login")
def login(body: LoginIn, request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    _check_rate(ip)
    if not hmac.compare_digest(body.pin.encode(), PIN.encode()):
        _fails.setdefault(ip, []).append(time.time())
        raise HTTPException(401, "PIN greșit.")
    response.set_cookie(
        "rota_auth",
        _token(),
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"ok": True}


@app.get("/api/state", dependencies=[Depends(require_auth)])
def state():
    with tx() as c:
        outings = load_outings(c)
    stats = compute_stats(MEMBERS, outings)
    return {
        "members": MEMBERS,
        "stats": [stats[m] for m in MEMBERS],
        "outings": list(reversed(outings)),
    }


@app.post("/api/next", dependencies=[Depends(require_auth)])
def next_payer(body: PresentIn):
    _validate_present(body.present)
    with tx() as c:
        stats = compute_stats(MEMBERS, load_outings(c))
    cands = candidates(stats, body.present)
    order = ranking(stats, body.present)
    return {
        "candidates": cands,
        "tie": len(cands) > 1,
        "ranking": [{"name": m, "balance": stats[m]["balance"]} for m in order],
    }


@app.post("/api/outings", dependencies=[Depends(require_auth)])
def create_outing(body: OutingIn):
    try:
        day = dt.date.fromisoformat(body.day)
    except ValueError:
        raise HTTPException(400, "Data nu e validă.")
    restaurant = body.restaurant.strip()
    if not (1 <= len(restaurant) <= 80):
        raise HTTPException(400, "Scrie numele restaurantului (maxim 80 de caractere).")
    _validate_present(body.present)
    if body.entered_by is not None and body.entered_by not in MEMBERS:
        raise HTTPException(400, "Nume necunoscut la „introdus de”.")

    with tx(write=True) as c:
        stats = compute_stats(MEMBERS, load_outings(c))
        cands = candidates(stats, body.present)
        draw = None
        manual = False
        if body.payer:
            if body.payer not in body.present:
                raise HTTPException(400, "Cine plătește trebuie să fie printre cei prezenți.")
            payer = body.payer
            manual = payer not in cands
        elif len(cands) > 1:
            payer = secrets.choice(cands)
            draw = {"candidates": cands, "drawn": payer}
        else:
            payer = cands[0]
        cur = c.execute(
            "INSERT INTO outings (date, restaurant, attendees, payer, draw, manual, "
            "entered_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                day.isoformat(),
                restaurant,
                json.dumps(body.present, ensure_ascii=False),
                payer,
                json.dumps(draw, ensure_ascii=False) if draw else None,
                int(manual),
                body.entered_by,
                dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        row = c.execute("SELECT * FROM outings WHERE id=?", (cur.lastrowid,)).fetchone()
    return _row(row)


@app.delete("/api/outings/{outing_id}", status_code=204, dependencies=[Depends(require_auth)])
def delete_outing(outing_id: int):
    with tx(write=True) as c:
        cur = c.execute(
            "UPDATE outings SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
            (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), outing_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Ieșirea nu există.")
    return Response(status_code=204)


@app.get("/api/export", dependencies=[Depends(require_auth)])
def export():
    with tx() as c:
        rows = c.execute("SELECT * FROM outings ORDER BY id").fetchall()
    return [dict(r) for r in rows]
