"""Pure-pandas checks used by the Streamlit app and the tests.

Each function returns a DataFrame of findings (empty = clean).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

WAITING_PERIOD_DAYS = 90
ENROL_WINDOW_DAYS = 30
FULL_TIME_ONLY_PLANS = {"Health Plus", "Pension Match"}


# ---------- 1. Invoice check ----------
def invoice_check(invoice: pd.DataFrame, contracts: pd.DataFrame, employees: pd.DataFrame,
                  month_start: date) -> pd.DataFrame:
    findings = []
    rates = {(r.provider, r.plan): r.contract_rate_eur for r in contracts.itertuples()}
    emp = employees.drop_duplicates("employee_id").set_index("employee_id")

    # duplicate lines
    dups = invoice[invoice.duplicated(["employee_id", "plan", "month"], keep="first")]
    for r in dups.itertuples():
        findings.append((r.employee_id, "Duplicate invoice line", r.billed_rate_eur, "Remove from invoice"))

    for r in invoice.drop_duplicates(["employee_id", "plan", "month"]).itertuples():
        contract = rates.get((r.provider, r.plan))
        if contract is not None and round(r.billed_rate_eur - contract, 2) != 0:
            findings.append((r.employee_id, f"Rate differs from contract ({contract:.2f})",
                             round(r.billed_rate_eur - contract, 2), "Query with provider"))
        if r.employee_id not in emp.index:
            findings.append((r.employee_id, "Billed member not in employee file", r.billed_rate_eur,
                             "Query with provider / People Ops"))
            continue
        e = emp.loc[r.employee_id]
        if e.end_date and pd.to_datetime(e.end_date).date() < month_start:
            findings.append((r.employee_id, f"Leaver still billed (left {e.end_date})",
                             r.billed_rate_eur, "Request credit note"))

    # active members expected on an invoice but missing
    billed = set(invoice.employee_id)
    for e in employees.drop_duplicates("employee_id").itertuples():
        if e.status == "Active" and e.employee_id not in billed:
            findings.append((e.employee_id, "Active member missing from invoice", 0.0,
                             "Check enrolment, then confirm with provider"))
    return pd.DataFrame(findings, columns=["employee_id", "issue", "amount_eur", "action"])


# ---------- 2. Eligibility and data quality ----------
def eligibility_check(employees: pd.DataFrame) -> pd.DataFrame:
    findings = []
    for r in employees.itertuples():
        start = pd.to_datetime(r.start_date).date()
        enrol = pd.to_datetime(r.enrolment_date).date() if r.enrolment_date else None
        if enrol and enrol < start + timedelta(days=WAITING_PERIOD_DAYS):
            findings.append((r.employee_id, "Enrolled before waiting period ended", "Review start date or reverse enrolment"))
        if r.plan in FULL_TIME_ONLY_PLANS and r.employment_type != "Full-time":
            findings.append((r.employee_id, f"{r.employment_type} on full-time-only plan {r.plan}", "Confirm eligibility rules"))
        if r.status == "Left" and not r.end_date:
            findings.append((r.employee_id, "Leaver without leaver date", "Get leaver date from People Ops"))
    dup = employees[employees.duplicated(["name", "start_date", "country"], keep=False)]
    for r in dup.itertuples():
        findings.append((r.employee_id, "Possible duplicate record", "Merge or delete after checking"))
    return pd.DataFrame(findings, columns=["employee_id", "issue", "action"])


def corrected_file(employees: pd.DataFrame) -> pd.DataFrame:
    """Drop exact-duplicate people and flag rows that need manual review."""
    out = employees.drop_duplicates(["name", "start_date", "country"], keep="first").copy()
    issues = eligibility_check(out)
    out["needs_review"] = out.employee_id.isin(issues.employee_id)
    return out


# ---------- 3. Request router and reminders ----------
ROUTES = [  # (category, keywords, owner, sla_hours)
    ("Leaver", ["last day", "leaving", "resign", "leaver"], "People Ops + Payroll", 24),
    ("Dependants and life events", ["spouse", "partner", "married", "baby", "dependant"], "Benefits (Total Rewards)", 48),
    ("Claims", ["claim", "rejected", "pre-approval", "reimburse"], "Insurer (broker escalation)", 48),
    ("Payroll deduction", ["payslip", "deduction", "salary"], "Payroll", 24),
    ("Enrolment and eligibility", ["eligible", "enrol", "join", "switch", "add"], "Benefits (Total Rewards)", 72),
    ("Pension", ["pension"], "Benefits (Total Rewards)", 72),
    ("Admin", ["card", "address", "document"], "Benefits (Total Rewards)", 72),
]


def route_requests(requests: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in requests.itertuples():
        text = r.message.lower()
        cat, owner, sla = "Unclassified", "Benefits (Total Rewards): manual triage", 72
        for c, kws, o, s in ROUTES:
            if any(k in text for k in kws):
                cat, owner, sla = c, o, s
                break
        rows.append((r.request_id, r.employee_id, cat, owner, sla, r.message))
    return pd.DataFrame(rows, columns=["request_id", "employee_id", "category", "owner", "sla_hours", "message"])


def reminders(providers: pd.DataFrame, employees: pd.DataFrame, today: date,
              renewal_window_days: int = 90) -> pd.DataFrame:
    out = []
    for p in providers.itertuples():
        days = (pd.to_datetime(p.renewal_date).date() - today).days
        if 0 <= days <= renewal_window_days:
            out.append(("Renewal", p.provider, p.renewal_date, days,
                        f"Renewal for {p.contract} in {days} days: request quote and confirm headcount."))
    for e in employees.itertuples():
        start = pd.to_datetime(e.start_date).date()
        deadline = start + timedelta(days=WAITING_PERIOD_DAYS + ENROL_WINDOW_DAYS)
        days = (deadline - today).days
        if e.status == "Active" and 0 <= days <= 14:
            out.append(("Enrolment deadline", e.employee_id, deadline.isoformat(), days,
                        f"{e.employee_id}: enrolment window closes in {days} days."))
    return pd.DataFrame(out, columns=["type", "subject", "due", "days_left", "draft_message"])
