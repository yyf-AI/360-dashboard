import json, re, sys
sys.stdout.reconfigure(encoding='utf-8')

# Load advertiser mapping from postback query
with open(r'C:\Users\Mi\.claude\projects\C--Users-Mi\a90c26ca-25a4-4742-9aba-a0eb1567530f\tool-results\call_ac8f0b30b0af4df1bc9081bf.json', 'r', encoding='utf-8') as f:
    raw = json.load(f)

result = json.loads(raw[0]['text'])
adv_map = {}
for row in result['rows']:
    cid = str(row[0])
    name = row[1] or ''
    adv_id = row[2] or ''
    if name and cid not in adv_map:
        adv_map[cid] = f'{name}({adv_id})' if adv_id else name

print(f'Advertiser mapping: {len(adv_map)} campaigns')

# Load JS data
with open(r'C:\Users\Mi\360_dashboard\360_dashboard_data.js', 'r', encoding='utf-8') as f:
    content = f.read()

match = re.search(r'const\s+DATA\s*=\s*(\[.*?\]);', content, re.DOTALL)
data = json.loads(match.group(1))

# Fix empty advertiser fields for 0708-0710
fixed = 0
for record in data:
    if record.get('period') in ('0708', '0709', '0710') and not record.get('advertiser'):
        cid = record.get('campaign_id', '')
        if cid in adv_map:
            record['advertiser'] = adv_map[cid]
            fixed += 1

print(f'Fixed {fixed} records')

# Verify
for period in ['0708', '0709', '0710']:
    records = [r for r in data if r.get('period') == period]
    empty = [r for r in records if not r.get('advertiser')]
    print(f'{period}: {len(records)} records, {len(empty)} still empty')

# Write back
js_content = 'const DATA = ' + json.dumps(data, ensure_ascii=False, indent=2) + ';'
with open(r'C:\Users\Mi\360_dashboard\360_dashboard_data.js', 'w', encoding='utf-8') as f:
    f.write(js_content)

print('Done!')
