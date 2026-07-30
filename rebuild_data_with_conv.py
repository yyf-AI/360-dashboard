import json
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

REVENUE_RESULT = r"C:\Users\Mi\.claude\projects\C--Users-Mi\cae93e01-df6a-4e69-9cf8-ef510b10ec8b\tool-results\call_e1d75175c0ce4da38bde0794.json"
POSTBACK_RESULT = r"C:\Users\Mi\.claude\projects\C--Users-Mi\cae93e01-df6a-4e69-9cf8-ef510b10ec8b\tool-results\call_514d49af1c8d4062bd0a2f4d.json"
JS_PATH = r"C:\Users\Mi\360_dashboard\360_dashboard_data.js"

# 1. Load revenue data
with open(REVENUE_RESULT, 'r', encoding='utf-8') as f:
    raw = json.load(f)
result = json.loads(raw[0]['text'])
rows = result['rows']
total_rows = result['totalRows']
print(f"Loaded {len(rows)} rows (total: {total_rows})")

# 2. Load postback data
with open(POSTBACK_RESULT, 'r', encoding='utf-8') as f:
    raw_pb = json.load(f)
pb_result = json.loads(raw_pb[0]['text'])
pb_rows = pb_result['rows']
campaign_info = {}
for row in pb_rows:
    cid, pkg, adv = row
    if cid:
        campaign_info[str(cid)] = {
            'package_name': pkg or '',
            'advertiser_name': adv or ''
        }
print(f"Loaded {len(pb_rows)} postback records")

# 3. Aggregate by (date, campaign_id)
campaigns = defaultdict(lambda: {
    'revenue': 0, 'conversions': 0, 'block': 0, 'pa': 0,
    'pub_rev': {}, 'pub_conv': {}, 'pub_block': {}, 'pub_pa': {}
})

for row in rows:
    date, cid, pub_id, rev, conv, block, pa = row
    if not cid or cid == '':
        continue
    period = str(date)[4:]
    key = (period, cid)

    campaigns[key]['revenue'] += rev
    campaigns[key]['conversions'] += conv
    campaigns[key]['block'] += block
    campaigns[key]['pa'] += pa

    # Per publisher detailed fields
    campaigns[key]['pub_rev'][pub_id] = round(rev, 2)
    campaigns[key]['pub_conv'][pub_id] = conv
    campaigns[key]['pub_block'][pub_id] = block
    campaigns[key]['pub_pa'][pub_id] = pa

print(f"Generated {len(campaigns)} campaign entries")
periods = sorted(set(p for p, c in campaigns.keys()))
print(f"Periods: {periods}")

# 4. Build JS entries
new_entries = []
for (period, cid), data in campaigns.items():
    total_denom = data['block'] + data['conversions']
    if total_denom > 0:
        overall_fraud = (data['pa'] + data['block']) / total_denom
        overall_block = data['block'] / total_denom
        overall_pa = data['pa'] / total_denom
    else:
        overall_fraud = overall_block = overall_pa = 0

    # Build per-publisher fraud rates
    pub_fraud = {}
    for pub_id in data['pub_rev'].keys():
        d = data
        pub_denom = d['pub_block'].get(pub_id, 0) + d['pub_conv'].get(pub_id, 0)
        if pub_denom > 0:
            pub_fraud[pub_id] = round((d['pub_pa'].get(pub_id, 0) + d['pub_block'].get(pub_id, 0)) / pub_denom, 4)
        else:
            pub_fraud[pub_id] = 0

    info = campaign_info.get(cid, {})

    entry = {
        "campaign_id": cid,
        "advertiser": info.get('advertiser_name', ''),
        "package_name": info.get('package_name', ''),
        "revenue": round(data['revenue'], 2),
        "conversions": data['conversions'],
        "overall_fraud": round(overall_fraud, 4),
        "overall_block": round(overall_block, 4),
        "overall_pa": round(overall_pa, 4),
        "pub_fraud": pub_fraud,
        "pub_rev": data['pub_rev'],
        "pub_conv": data['pub_conv'],
        "pub_block": data['pub_block'],
        "pub_pa": data['pub_pa'],
        "period": period,
        "days": 1
    }
    new_entries.append(entry)

new_entries.sort(key=lambda x: (x['period'], -x['revenue']))
print(f"Built {len(new_entries)} entries")

# 5. Write JS
new_js = f"const DATA = {json.dumps(new_entries, ensure_ascii=False)};\n"
with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(new_js)
print(f"Written to {JS_PATH}")

# Verify
has_conv = sum(1 for e in new_entries if 'pub_conv' in e)
has_262 = sum(1 for e in new_entries if '1000262' in e.get('pub_conv', {}))
print(f"Entries with pub_conv: {has_conv}")
print(f"Entries with 262 in pub_conv: {has_262}")
print(f"All periods: {sorted(set(e['period'] for e in new_entries))}")
