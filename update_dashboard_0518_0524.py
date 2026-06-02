import json
import re

RESULT_PATH = r"C:\Users\Mi\.claude\projects\C--Users-Mi\1019789b-31f3-47ee-9d87-5be59be0d64e\tool-results\call_910df5b406ce456bb8fe5057.json"
JS_PATH = r"C:\Users\Mi\360_dashboard\360_dashboard_data.js"

TARGET_PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260']

# 1. Load query result
with open(RESULT_PATH, 'r', encoding='utf-8') as f:
    raw = json.load(f)
result = json.loads(raw[0]['text'])
rows = result['rows']
print(f"Loaded {len(rows)} rows")

# 2. Aggregate by (date, campaign_id)
from collections import defaultdict
campaigns = defaultdict(lambda: {
    'revenue': 0, 'conversions': 0, 'block': 0, 'pa': 0,
    'parent_name': '', 'package_name': '',
    'pub_fraud': {}, 'pub_rev': {}
})

for row in rows:
    date, cid, parent_name, pkg, pub_id, rev, conv, block, pa = row
    period = str(date)[4:]  # "0518"
    key = (period, cid)

    campaigns[key]['revenue'] += rev
    campaigns[key]['conversions'] += conv
    campaigns[key]['block'] += block
    campaigns[key]['pa'] += pa
    if parent_name:
        campaigns[key]['parent_name'] = parent_name
    if pkg:
        campaigns[key]['package_name'] = pkg

    # Per publisher fraud
    total_denom = block + conv
    if total_denom > 0:
        fraud = (pa + block) / total_denom
    else:
        fraud = 0
    campaigns[key]['pub_fraud'][pub_id] = round(fraud, 4)
    campaigns[key]['pub_rev'][pub_id] = round(rev, 2)

# 3. Build JS entries
new_entries = []
for (period, cid), data in campaigns.items():
    total_denom = data['block'] + data['conversions']
    if total_denom > 0:
        overall_fraud = (data['pa'] + data['block']) / total_denom
        overall_block = data['block'] / total_denom
        overall_pa = data['pa'] / total_denom
    else:
        overall_fraud = overall_block = overall_pa = 0

    entry = {
        "campaign_id": cid,
        "advertiser": data['parent_name'],
        "package_name": data['package_name'],
        "revenue": round(data['revenue'], 2),
        "conversions": data['conversions'],
        "overall_fraud": round(overall_fraud, 4),
        "overall_block": round(overall_block, 4),
        "overall_pa": round(overall_pa, 4),
        "pub_fraud": data['pub_fraud'],
        "pub_rev": data['pub_rev'],
        "period": period,
        "days": 1
    }
    new_entries.append(entry)

print(f"Generated {len(new_entries)} entries for periods: {sorted(set(e['period'] for e in new_entries))}")

# 4. Load existing JS data and merge
with open(JS_PATH, 'r', encoding='utf-8') as f:
    js_content = f.read()

# Extract existing DATA array
match = re.search(r'const DATA = (\[.*?\]);', js_content, re.DOTALL)
if match:
    existing_data = json.loads(match.group(1))
else:
    existing_data = []

print(f"Existing entries: {len(existing_data)}")

# Remove old entries for the same periods
new_periods = set(e['period'] for e in new_entries)
filtered = [e for e in existing_data if e.get('period') not in new_periods]
print(f"After removing old periods {sorted(new_periods)}: {len(filtered)} entries")

# Append new entries
filtered.extend(new_entries)
filtered.sort(key=lambda x: (x['period'], -x['revenue']))
print(f"Final total: {len(filtered)} entries")

# 5. Write back
new_js = f"const DATA = {json.dumps(filtered, ensure_ascii=False)};\n"
with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(new_js)

print(f"Written to {JS_PATH}")

# 6. Print summary per period
from collections import defaultdict as dd
period_stats = dd(lambda: {'rev': 0, 'conv': 0, 'camps': set()})
for e in new_entries:
    p = e['period']
    period_stats[p]['rev'] += e['revenue']
    period_stats[p]['conv'] += e['conversions']
    period_stats[p]['camps'].add(e['campaign_id'])

print("\n=== Summary ===")
for p in sorted(period_stats.keys()):
    s = period_stats[p]
    print(f"  {p}: ${s['rev']:,.0f}  conv={s['conv']:,}  campaigns={len(s['camps'])}")
