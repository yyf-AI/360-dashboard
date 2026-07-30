import json
import re
from collections import defaultdict

RESULT_PATH = r"C:\Users\Mi\.claude\projects\C--Users-Mi\cae93e01-df6a-4e69-9cf8-ef510b10ec8b\tool-results\call_6f131dd06a0e46c6b6e7dba9.json"
POSTBACK_PATH = r"C:\Users\Mi\.claude\projects\C--Users-Mi\cae93e01-df6a-4e69-9cf8-ef510b10ec8b\tool-results\call_514d49af1c8d4062bd0a2f4d.json"
JS_PATH = r"C:\Users\Mi\360_dashboard\360_dashboard_data.js"

TARGET_PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260']

# 1. Load query results
with open(RESULT_PATH, 'r', encoding='utf-8') as f:
    raw = json.load(f)
result = json.loads(raw[0]['text'])
rows = result['rows']
print(f"Loaded {len(rows)} revenue rows")

# Load postback data (campaign_id -> package_name, advertiser_name)
with open(POSTBACK_PATH, 'r', encoding='utf-8') as f:
    raw_pb = json.load(f)
pb_result = json.loads(raw_pb[0]['text'])
pb_rows = pb_result['rows']
print(f"Loaded {len(pb_rows)} postback rows")

# Build campaign_id -> (package_name, advertiser_name) map
campaign_info = {}
for row in pb_rows:
    cid, pkg, adv = row
    if cid:
        campaign_info[str(cid)] = {
            'package_name': pkg or '',
            'advertiser_name': adv or ''
        }

# 2. Aggregate by (date, campaign_id)
campaigns = defaultdict(lambda: {
    'revenue': 0, 'conversions': 0, 'block': 0, 'pa': 0,
    'pub_fraud': {}, 'pub_rev': {}
})

for row in rows:
    date, cid, pub_id, rev, conv, block, pa = row

    # Skip summary rows (empty campaign_id)
    if not cid or cid == '':
        continue

    period = str(date)[4:]  # "0723"
    key = (period, cid)

    campaigns[key]['revenue'] += rev
    campaigns[key]['conversions'] += conv
    campaigns[key]['block'] += block
    campaigns[key]['pa'] += pa

    # Per publisher fraud
    total_denom = block + conv
    if total_denom > 0:
        fraud = (pa + block) / total_denom
    else:
        fraud = 0
    campaigns[key]['pub_fraud'][pub_id] = round(fraud, 4)
    campaigns[key]['pub_rev'][pub_id] = round(rev, 2)

# 3. Build JS entries with package_name and advertiser from postback
new_entries = []
for (period, cid), data in campaigns.items():
    total_denom = data['block'] + data['conversions']
    if total_denom > 0:
        overall_fraud = (data['pa'] + data['block']) / total_denom
        overall_block = data['block'] / total_denom
        overall_pa = data['pa'] / total_denom
    else:
        overall_fraud = overall_block = overall_pa = 0

    # Get package_name and advertiser from postback info
    info = campaign_info.get(cid, {})
    package_name = info.get('package_name', '')
    advertiser = info.get('advertiser_name', '')

    entry = {
        "campaign_id": cid,
        "advertiser": advertiser,
        "package_name": package_name,
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

print(f"Updated {JS_PATH}")

# Show periods
periods = sorted(set(e['period'] for e in filtered))
print(f"All periods: {periods}")

# Show sample entries for verification
print("\n=== Sample entries for 0723 ===")
for e in new_entries[:3]:
    if e['period'] == '0723':
        print(f"  campaign_id: {e['campaign_id']}")
        print(f"  package_name: {e['package_name']}")
        print(f"  advertiser: {e['advertiser']}")
        print(f"  revenue: {e['revenue']}")
        print()
