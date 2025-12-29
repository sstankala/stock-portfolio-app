import os
import requests
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Stock Portfolio", layout="wide")
st.title("📈 Stock Portfolio (Client)")

# Health
try:
    h = requests.get(f"{API_URL}/health", timeout=3).json()
    st.success(f"API: {h['status']}")
except Exception as e:
    st.error(f"API not reachable at {API_URL}: {e}")
    st.stop()

st.subheader("Holdings")
resp = requests.get(f"{API_URL}/holdings").json()
df = pd.DataFrame(resp)
st.dataframe(df if not df.empty else pd.DataFrame(columns=["symbol","shares","avg_cost"]), use_container_width=True)

st.subheader("Place a Trade")
col1, col2, col3, col4 = st.columns(4)
symbol = col1.text_input("Symbol", value="AAPL")
side = col2.selectbox("Side", ["buy", "sell"])
shares = col3.number_input("Shares", min_value=0.0001, value=1.0, step=1.0)
price = col4.number_input("Price", min_value=0.01, value=100.0, step=1.0)

if st.button("Submit Trade"):
    payload = {"symbol": symbol, "side": side, "shares": float(shares), "price": float(price)}
    r = requests.post(f"{API_URL}/trade", json=payload)
    if r.status_code == 200:
        st.success("Trade submitted.")
        st.rerun()
    else:
        st.error(r.text)
