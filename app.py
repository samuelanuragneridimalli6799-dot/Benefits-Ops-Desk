from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import checks

DATA = Path(__file__).parent / "data"

st.set_page_config(page_title="Benefits Ops Desk", page_icon="🧾", layout="wide")
st.title("Benefits Ops Desk")
st.caption("Demo built on fully synthetic data. No real employee, vendor or company data is used.")


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name, keep_default_na=False)


emp = load("employees.csv")
con = load("contract_rates.csv")
inv = load("invoice.csv")
req = load("requests.csv")
prov = load("providers.csv")

tab1, tab2, tab3 = st.tabs(["1. Invoice check", "2. Eligibility and leaver checks", "3. Request router and reminders"])

with tab1:
    st.subheader("Vendor invoice vs contract rates and headcount")
    up = st.file_uploader("Upload an invoice CSV (or use the sample)", type="csv", key="inv")
    invoice = pd.read_csv(up) if up else inv
    month = st.date_input("Invoice month start", value=date(2026, 10, 1))
    f = checks.invoice_check(invoice, con, emp, month)
    c1, c2, c3 = st.columns(3)
    c1.metric("Invoice lines", len(invoice))
    c2.metric("Findings", len(f))
    c3.metric("Value at risk (EUR)", f"{f[f.amount_eur > 0].amount_eur.sum():,.2f}")
    st.dataframe(f, width='stretch', hide_index=True)
    st.download_button("Download findings CSV", f.to_csv(index=False), "invoice_findings.csv")

with tab2:
    st.subheader("Eligibility, leaver and data-quality scan")
    f2 = checks.eligibility_check(emp)
    st.metric("Records scanned / findings", f"{len(emp)} / {len(f2)}")
    st.dataframe(f2, width='stretch', hide_index=True)
    fixed = checks.corrected_file(emp)
    st.download_button("Download corrected file (duplicates removed, review flag added)",
                       fixed.to_csv(index=False), "employees_corrected.csv")

with tab3:
    st.subheader("Request routing")
    routed = checks.route_requests(req)
    st.dataframe(routed, width='stretch', hide_index=True)
    st.bar_chart(routed.category.value_counts())
    st.subheader("Reminders")
    today = st.date_input("Today", value=date(2026, 10, 27))
    window = st.slider("Renewal reminder window (days)", 30, 180, 90)
    rem = checks.reminders(prov, emp, today, window)
    st.dataframe(rem, width='stretch', hide_index=True)
    st.info("The same routing logic runs as an n8n workflow in n8n/request_router.json.")
