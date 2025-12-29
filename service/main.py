from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field 
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db import SessionLocal, engine
from models import Base, Holding

app = FastAPI(title="Portfolio Microservice")

# Create tables (simple for demo; migrations are better for prod)
Base.metadata.create_all(bind=engine)

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
    sym = t.symbol.upper()
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
            # keep avg_cost as-is for demo
            if float(h.shares) == 0:
                db.delete(h)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Trade failed.")
        return {"ok": True}
