"""Generate fully synthetic data for the Benefits Ops Desk demo.

Every name, ID, rate and date is invented. Errors are planted on purpose
(seeded, so results are reproducible) so the checks have something to find.
"""
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 42
REF_DATE = date(2026, 10, 1)  # invoice month start
OUT = Path(__file__).parent / "data"

FIRST = ["Aino", "Mart", "Liis", "Karl", "Maria", "Tõnu", "Eva", "Jaan", "Kadri", "Priit",
         "Helen", "Andres", "Sofia", "Oskar", "Nora", "Lauri", "Mia", "Rasmus", "Elena", "Ivo"]
LAST = ["Tamm", "Saar", "Kask", "Mägi", "Ilves", "Rebane", "Kuusk", "Pärn", "Lepik", "Koppel",
        "Sepp", "Mets", "Oja", "Raud", "Vaher"]
COUNTRIES = ["Estonia", "Poland", "Portugal", "Germany"]
PLANS = {  # plan -> (provider, contract monthly rate EUR, needs full-time)
    "Health Plus": ("NordCare Insurance", 48.00, True),
    "Dental Basic": ("NordCare Insurance", 12.50, False),
    "Pension Match": ("Baltic Pensions", 30.00, True),
}


def build():
    rng = random.Random(SEED)
    rows = []
    for i in range(1, 61):
        start = REF_DATE - timedelta(days=rng.randint(20, 1400))
        emp_type = rng.choices(["Full-time", "Part-time", "Contractor"], [80, 10, 10])[0]
        status = "Active"
        end = None
        if rng.random() < 0.10:
            status = "Left"
            end = REF_DATE - timedelta(days=rng.randint(5, 80))
        rows.append({
            "employee_id": f"E{1000 + i}",
            "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "country": rng.choice(COUNTRIES),
            "employment_type": emp_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if end else "",
            "status": status,
            "plan": "",
            "enrolment_date": "",
        })
    emp = pd.DataFrame(rows)

    # Enrol: everyone gets Health Plus unless contractor/part-time; some get Dental
    plans, enrol = [], []
    for _, r in emp.iterrows():
        start = date.fromisoformat(r.start_date)
        eligible_from = start + timedelta(days=90)
        if r.employment_type == "Contractor":
            plans.append("Dental Basic")
        else:
            plans.append("Health Plus")
        enrol.append(max(eligible_from, start).isoformat())
    emp["plan"] = plans
    emp["enrolment_date"] = enrol

    # --- planted errors in the employee file ---
    # 1) enrolled before the 90-day waiting period ends
    for idx in (3, 17):
        s = date.fromisoformat(emp.loc[idx, "start_date"])
        emp.loc[idx, "enrolment_date"] = (s + timedelta(days=20)).isoformat()
    # 2) contractor on a plan they are not eligible for (Pension Match needs full-time)
    emp.loc[emp.index[emp.employment_type == "Contractor"][0], "plan"] = "Pension Match"
    # 3) part-time on Health Plus (needs full-time)
    pt = emp.index[emp.employment_type == "Part-time"]
    if len(pt):
        emp.loc[pt[0], "plan"] = "Health Plus"
    # 4) leaver with no leaver date
    emp.loc[emp.index[emp.status == "Left"][0], "end_date"] = ""
    # 5) duplicate employee record
    dup = emp.iloc[8].copy()
    dup["employee_id"] = "E1099"
    emp = pd.concat([emp, dup.to_frame().T], ignore_index=True)

    # --- contract rates ---
    contracts = pd.DataFrame(
        [{"provider": p, "plan": plan, "contract_rate_eur": rate} for plan, (p, rate, _) in PLANS.items()]
    )

    # --- invoice (member level, one provider batch) ---
    inv = []
    for _, r in emp.iterrows():
        if r.employee_id == "E1099":
            continue
        provider, rate, _ = PLANS[r.plan]
        inv.append({"invoice_id": "INV-2026-10-NC", "month": "2026-10", "employee_id": r.employee_id,
                    "provider": provider, "plan": r.plan, "billed_rate_eur": rate})
    inv = pd.DataFrame(inv)
    # planted invoice errors
    inv.loc[5, "billed_rate_eur"] = inv.loc[5, "billed_rate_eur"] + 6.0      # overbilled rate
    inv.loc[22, "billed_rate_eur"] = inv.loc[22, "billed_rate_eur"] + 6.0    # overbilled rate
    inv = pd.concat([inv, inv.iloc[[10]]], ignore_index=True)                # duplicate line
    inv = pd.concat([inv, pd.DataFrame([{                                    # unknown member
        "invoice_id": "INV-2026-10-NC", "month": "2026-10", "employee_id": "E9001",
        "provider": "NordCare Insurance", "plan": "Health Plus", "billed_rate_eur": 48.0}])],
        ignore_index=True)
    # drop one active member so a joiner/active member is missing from the invoice
    missing_id = emp[(emp.status == "Active") & (emp.plan == "Health Plus")].iloc[4].employee_id
    inv = inv[inv.employee_id != missing_id].reset_index(drop=True)

    # --- benefits requests ---
    reqs = [
        ("I'm moving to Portugal next month, how do I update my address for the health plan?", "E1004"),
        ("When can I add my partner to Health Plus?", "E1011"),
        ("My last day is 31 October, what happens to my pension and insurance?", "E1019"),
        ("I got married, I want to add my spouse as a dependant", "E1025"),
        ("Please send me my insurance card, I lost it", "E1031"),
        ("The dentist rejected my claim and asked for pre-approval", "E1040"),
        ("Is the pension match paid on bonus?", "E1044"),
        ("New joiner here, which benefits am I eligible for and by when must I enrol?", "E1052"),
        ("Can I switch from Dental Basic to Health Plus mid-year?", "E1007"),
        ("I think my payslip shows the wrong benefits deduction", "E1015"),
    ]
    req = pd.DataFrame([
        {"request_id": f"R{200 + i}", "received": (REF_DATE + timedelta(days=i)).isoformat(),
         "employee_id": e, "message": m} for i, (m, e) in enumerate(reqs)])

    # --- provider renewals ---
    prov = pd.DataFrame([
        {"provider": "NordCare Insurance", "contract": "Group health and dental",
         "renewal_date": "2026-12-31", "contact": "account-manager@nordcare.example"},
        {"provider": "Baltic Pensions", "contract": "Pension match scheme",
         "renewal_date": "2027-03-31", "contact": "client-services@balticpensions.example"},
    ])

    OUT.mkdir(exist_ok=True)
    emp.to_csv(OUT / "employees.csv", index=False)
    contracts.to_csv(OUT / "contract_rates.csv", index=False)
    inv.to_csv(OUT / "invoice.csv", index=False)
    req.to_csv(OUT / "requests.csv", index=False)
    prov.to_csv(OUT / "providers.csv", index=False)
    print("wrote", [p.name for p in OUT.iterdir()])


if __name__ == "__main__":
    build()
