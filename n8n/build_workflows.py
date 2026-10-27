"""Builds the n8n workflow JSON files so the routing rules stay in one place."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import checks

routes_js = json.dumps([[c, k, o, s] for c, k, o, s in checks.ROUTES])

router_code = f"""const ROUTES = {routes_js};
return $input.all().map(item => {{
  const text = String(item.json.message || '').toLowerCase();
  let category = 'Unclassified', owner = 'Benefits (Total Rewards): manual triage', sla_hours = 72;
  for (const [c, kws, o, s] of ROUTES) {{
    if (kws.some(k => text.includes(k))) {{ category = c; owner = o; sla_hours = s; break; }}
  }}
  return {{ json: {{ request_id: item.json.request_id, employee_id: item.json.employee_id, category, owner, sla_hours, message: item.json.message }} }};
}});"""

reminder_code = """const today = new Date();
const providers = [
  { provider: 'NordCare Insurance', contract: 'Group health and dental', renewal: '2026-12-31' },
  { provider: 'Baltic Pensions', contract: 'Pension match scheme', renewal: '2027-03-31' }
];
const out = [];
for (const p of providers) {
  const days = Math.ceil((new Date(p.renewal) - today) / 86400000);
  if (days >= 0 && days <= 90) {
    out.push({ json: { type: 'Renewal', provider: p.provider, days_left: days,
      draft_message: `Renewal for ${p.contract} in ${days} days: request quote and confirm headcount.` } });
  }
}
if (out.length === 0) out.push({ json: { type: 'None', draft_message: 'No renewals inside the window.' } });
return out;"""

error_code = """const e = $input.first().json;
return [{ json: { alert: `Workflow failed: ${e.workflow?.name}`, node: e.execution?.lastNodeExecuted,
  message: e.execution?.error?.message, url: e.execution?.url } }];"""

def code(name, js, pos):
    return {"parameters": {"jsCode": js}, "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}

router = {
  "name": "Benefits request router",
  "nodes": [
    {"parameters": {"httpMethod": "POST", "path": "benefits-request", "responseMode": "lastNode", "options": {}},
     "name": "Webhook: new benefits requests", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0],
     "webhookId": "benefits-request-demo"},
    {"parameters": {"fieldToSplitOut": "requests", "options": {}},
     "name": "Split requests", "type": "n8n-nodes-base.splitOut", "typeVersion": 1, "position": [220, 0]},
    code("Classify and route", router_code, [440, 0]),
  ],
  "connections": {
    "Webhook: new benefits requests": {"main": [[{"node": "Split requests", "type": "main", "index": 0}]]},
    "Split requests": {"main": [[{"node": "Classify and route", "type": "main", "index": 0}]]},
  },
  "settings": {"executionOrder": "v1"},
}

reminders = {
  "name": "Benefits renewal reminders",
  "nodes": [
    {"parameters": {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1], "triggerAtHour": 8}]}},
     "name": "Every Monday 08:00", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0]},
    code("Find renewals inside 90 days", reminder_code, [220, 0]),
  ],
  "connections": {"Every Monday 08:00": {"main": [[{"node": "Find renewals inside 90 days", "type": "main", "index": 0}]]}},
  "settings": {"executionOrder": "v1"},
}

errors = {
  "name": "Flag failed workflows",
  "nodes": [
    {"parameters": {}, "name": "Error Trigger", "type": "n8n-nodes-base.errorTrigger", "typeVersion": 1, "position": [0, 0]},
    code("Format alert", error_code, [220, 0]),
  ],
  "connections": {"Error Trigger": {"main": [[{"node": "Format alert", "type": "main", "index": 0}]]}},
  "settings": {"executionOrder": "v1"},
}

here = Path(__file__).parent
for fname, wf in [("request_router.json", router), ("renewal_reminders.json", reminders), ("error_alert.json", errors)]:
    (here / fname).write_text(json.dumps(wf, indent=2, ensure_ascii=False))
    print("wrote", fname)
