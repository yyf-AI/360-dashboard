import json
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

RESULT_0726_0727 = r"C:\Users\Mi\.claude\projects\C--Users-Mi\cae93e01-df6a-4e69-9cf8-ef510b10ec8b\tool-results\call_24564671584344e29d8fa651.json"
POSTBACK_RESULT = r"C:\Users\Mi\.claude\projects\C--Users-Mi\cae93e01-df6a-4e69-9cf8-ef510b10ec8b\tool-results\call_514d49af1c8d4062bd0a2f4d.json"
JS_PATH = r"C:\Users\Mi\360_dashboard\360_dashboard_data.js"

# 1. Load existing0721-0725 data (already has pub_conv/pub_block/pub_pa)
with open(JS_PATH, 'r', encoding='utf-8') as f:
    content = f.read()
match = re.search(r'const DATA = (\[.*?\]);', content, re.DOTALL)
existing_data = json.loads(match.group(1))
print(f"Existing data: {len(existing_data)} entries, periods: {sorted(set(d['period'] for d in existing_data))}")

# 2. Load0726-0727 query result
with open(RESULT_0726_0727, 'r', encoding='utf-8') as f:
    raw = json.load(f)
result = json.loads(raw[0]['text'])
rows = result['rows']
print(f"0726-0727 rows: {len(rows)}")

# 3. Load postback data
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

# 4. Process0726-0727 data
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
    campaigns[key]['pub_rev'][pub_id] = round(rev, 2)
    campaigns[key]['pub_conv'][pub_id] = conv
    campaigns[key]['pub_block'][pub_id] = block
    campaigns[key]['pub_pa'][pub_id] = pa

# 5. Build JS entries for0726-0727
new_entries = []
for (period, cid), data in campaigns.items():
    total_denom = data['block'] + data['conversions']
    if total_denom > 0:
        overall_fraud = (data['pa'] + data['block']) / total_denom
        overall_block = data['block'] / total_denom
        overall_pa = data['pa'] / total_denom
    else:
        overall_fraud = overall_block = overall_pa = 0

    pub_fraud = {}
    for pub_id in data['pub_rev'].keys():
        pub_denom = data['pub_block'].get(pub_id, 0) + data['pub_conv'].get(pub_id, 0)
        if pub_denom > 0:
            pub_fraud[pub_id] = round((data['pub_pa'].get(pub_id, 0) + data['pub_block'].get(pub_id, 0)) / pub_denom, 4)
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

print(f"New entries for 0726-0727: {len(new_entries)}")

# 6. Merge: remove old0726-0727, append new
new_periods = set(e['period'] for e in new_entries)
filtered = [e for e in existing_data if e.get('period') not in new_periods]
filtered.extend(new_entries)
filtered.sort(key=lambda x: (x['period'], -x['revenue']))
print(f"Final: {len(filtered)} entries, periods: {sorted(set(d['period'] for d in filtered))}")

# 7. Write
new_js = f"const DATA = {json.dumps(filtered, ensure_ascii=False)};\n"
with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(new_js)

# Verify
has_conv = sum(1 for e in filtered if 'pub_conv' in e)
has_262 = sum(1 for e in filtered if '1000262' in e.get('pub_conv', {}))
print(f"Entries with pub_conv: {has_conv}")
print(f"Entries with 262 in pub_conv: {has_262}")
