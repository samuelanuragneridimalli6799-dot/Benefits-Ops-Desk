import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import checks  # noqa: E402

D = ROOT / "data"
emp = pd.read_csv(D / "employees.csv", keep_default_na=False)
inv = pd.read_csv(D / "invoice.csv")
con = pd.read_csv(D / "contract_rates.csv")
req = pd.read_csv(D / "requests.csv")
prov = pd.read_csv(D / "providers.csv")
MONTH = date(2026, 10, 1)


def issues(df):
    return " | ".join(df.issue)


def test_invoice_finds_planted_errors():
    f = checks.invoice_check(inv, con, emp, MONTH)
    text = issues(f)
    assert "Rate differs from contract" in text
    assert "Duplicate invoice line" in text
    assert "not in employee file" in text
    assert "missing from invoice" in text
    assert (f.issue.str.startswith("Rate differs")).sum() == 2


def test_eligibility_finds_planted_errors():
    f = checks.eligibility_check(emp)
    text = issues(f)
    assert "waiting period" in text
    assert "full-time-only plan" in text
    assert "Leaver without leaver date" in text
    assert "Possible duplicate" in text


def test_clean_data_gives_no_rate_findings():
    clean = inv.copy()
    clean["billed_rate_eur"] = clean.merge(con, on=["provider", "plan"])["contract_rate_eur"].values
    f = checks.invoice_check(clean.drop_duplicates(), con, emp, MONTH)
    assert not f.issue.str.startswith("Rate differs").any()


def test_router_covers_all_requests():
    r = checks.route_requests(req)
    assert len(r) == len(req)
    assert (r.category != "Unclassified").sum() >= 8
    leaver = r[r.message.str.contains("last day")].iloc[0]
    assert leaver.category == "Leaver"


def test_reminders_renewal_window():
    r = checks.reminders(prov, emp, date(2026, 10, 27))
    assert (r.type == "Renewal").any()
    assert "NordCare" in r[r.type == "Renewal"].iloc[0].subject
