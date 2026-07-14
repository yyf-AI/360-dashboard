import json
import re

MAPPING_PATH = r"C:\Users\Mi\.claude\projects\C--Users-Mi\00ab539a-07c6-4474-8527-2e540ffde549\tool-results\call_9530b102abf8437ba8159018.json"
JS_PATH = r"C:\Users\Mi\360_dashboard\360_dashboard_data.js"

# 1. Load mapping
with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
    raw = json.load(f)
result = json.loads(raw[0]['text'])
rows = result['rows']

adv_map = {}
for cid, adv_id, adv_name in rows:
    if adv_name and adv_id:
        adv_map[str(cid)] = f"{adv_name}({adv_id})"

print(f"Loaded {len(adv_map)} campaign->advertiser mappings")

# 2. Load JS data
with open(JS_PATH, 'r', encoding='utf-8') as f:
    js_content = f.read()

match = re.search(r'const DATA = (\[.*?\]);', js_content, re.DOTALL)
data = json.loads(match.group(1))
print(f"Loaded {len(data)} records")

# 3. Patch
patched = 0
still_empty = 0
for d in data:
    if not d.get('advertiser'):
        cid = str(d.get('campaign_id', ''))
        if cid in adv_map:
            d['advertiser'] = adv_map[cid]
            patched += 1
        else:
            still_empty += 1

print(f"Patched this run: {patched}")
print(f"Still empty: {still_empty}")

# 4. Write back
new_js = f"const DATA = {json.dumps(data, ensure_ascii=False)};\n"
with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(new_js)
print("Done")
