import os
import requests
from cachetools import TTLCache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db import SessionLocal, engine
from models import Base, Holding

app = FastAPI(title="Portfolio Microservice")

# Create tables (simple demo approach)
Base.metadata.create_all(bind=engine)

# Cache quotes to reduce rate-limit pain
price_cache = TTLCache(maxsize=512, ttl=30)  # 30 seconds


class TradeIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    side: str = Field(pattern="^(buy|sell)$")
    shares: float = Field(gt=0)
    price: float = Field(gt=0)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/holdings")
def get_holdings():
    with SessionLocal() as db:
        rows = db.execute(select(Holding)).scalars().all()
        return [
            {"symbol": r.symbol, "shares": float(r.shares), "avg_cost": float(r.avg_cost)}
            for r in rows
        ]


@app.post("/trade")
def trade(t: TradeIn):
    sym = t.symbol.upper().strip()
    with SessionLocal() as db:
        h = db.execute(select(Holding).where(Holding.symbol == sym)).scalar_one_or_none()

        if t.side == "buy":
            if h is None:
                h = Holding(symbol=sym, shares=t.shares, avg_cost=t.price)
                db.add(h)
            else:
                total_cost = float(h.shares) * float(h.avg_cost) + t.shares * t.price
                total_shares = float(h.shares) + t.shares
                h.shares = total_shares
                h.avg_cost = total_cost / total_shares

        else:  # sell
            if h is None or float(h.shares) < t.shares:
                raise HTTPException(status_code=400, detail="Not enough shares to sell.")
            h.shares = float(h.shares) - t.shares
            if float(h.shares) == 0:
                db.delete(h)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Trade failed.")
        return {"ok": True}


@app.get("/price/{symbol}")
def get_price(symbol: str):
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="FINNHUB_API_KEY not set")

    sym = symbol.upper().strip()
    if not sym:
        raise HTTPException(status_code=400, detail="Symbol required")

    if sym in price_cache:
        return {"symbol": sym, "source": "cache", **price_cache[sym]}

    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": sym, "token": api_key},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Quote provider error: {e}")

    # Finnhub returns current price in `c`
    c = data.get("c")
    if c in (None, 0):
        raise HTTPException(status_code=404, detail=f"No quote found for {sym}")

    payload = {
        "current": float(c),
        "change": float(data.get("d") or 0),
        "change_pct": float(data.get("dp") or 0),
        "high": float(data.get("h") or 0),
        "low": float(data.get("l") or 0),
        "open": float(data.get("o") or 0),
        "prev_close": float(data.get("pc") or 0),
    }
    price_cache[sym] = payload
    return {"symbol": sym, "source": "live", **payload}
