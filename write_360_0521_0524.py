import json
import urllib.request
import time
import os
from collections import defaultdict

# Load auth token
auth_path = os.path.expanduser('~/.feishu-mcp-pro/auth.json')
with open(auth_path, 'r') as f:
    auth = json.load(f)
token = auth['access_token']

SPREADSHEET = 'Appms4paQh298wtDRoHcmv9Gndg'
NUM_DAYS = 4  # 0521-0524
TARGET_PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260']
PUB_IDS = ['218','220','222','223','224','226','253','254','255','260']

# Load 360 data
RESULT_PATH = r"C:\Users\Mi\.claude\projects\C--Users-Mi\1019789b-31f3-47ee-9d87-5be59be0d64e\tool-results\call_2d8d25f8db20492ea9b0aafe.json"
with open(RESULT_PATH, 'r', encoding='utf-8') as f:
    raw = json.load(f)
result = json.loads(raw[0]['text'])
rows_360 = result['rows']
print(f"360 data: {len(rows_360)} rows")

# Load postback info
PB_PATH = r"C:\Users\Mi\.claude\projects\C--Users-Mi\1019789b-31f3-47ee-9d87-5be59be0d64e\tool-results\call_58a02491783f43518ea4ed83.json"
with open(PB_PATH, 'r', encoding='utf-8') as f:
    raw_pb = json.load(f)
result_pb = json.loads(raw_pb[0]['text'])
pb_info = {}
for row in result_pb['rows']:
    cid = str(row[0])
    pb_info[cid] = {'parent_name': row[1] or '', 'package_name': row[2] or ''}
print(f"Postback info: {len(pb_info)} campaigns")

# Aggregate by campaign_id
campaigns = defaultdict(lambda: {
    'revenue': 0, 'conversions': 0, 'block': 0, 'pa': 0,
    'parent_name': '', 'package_name': '',
    'pub_data': {}
})

for row in rows_360:
    cid, pub_id, rev, conv, block, pa = row
    cid = str(cid)
    campaigns[cid]['revenue'] += float(rev) if rev else 0
    campaigns[cid]['conversions'] += int(conv) if conv else 0
    campaigns[cid]['block'] += int(block) if block else 0
    campaigns[cid]['pa'] += int(pa) if pa else 0
    campaigns[cid]['pub_data'][pub_id] = {
        'revenue': float(rev) if rev else 0,
        'conversions': int(conv) if conv else 0,
        'block': int(block) if block else 0,
        'pa': int(pa) if pa else 0,
    }

# Merge postback info
for cid, data in campaigns.items():
    if cid in pb_info:
        data['parent_name'] = pb_info[cid]['parent_name']
        data['package_name'] = pb_info[cid]['package_name']

print(f"Unique campaigns: {len(campaigns)}")

# Sort by revenue desc
sorted_cids = sorted(campaigns.keys(), key=lambda x: -campaigns[x]['revenue'])

# Build output rows (53 columns: A-BA)
output_rows = []
for cid in sorted_cids:
    data = campaigns[cid]
    total_rev = data['revenue']
    total_conv = data['conversions']
    total_block = data['block']
    total_pa = data['pa']

    # Fraud rates for 10 publishers
    pub_fraud_rates = {}
    for pub_id in TARGET_PUBS:
        pd = data['pub_data'].get(pub_id, {})
        denom = pd.get('block', 0) + pd.get('conversions', 0)
        if denom > 0:
            pub_fraud_rates[pub_id] = (pd.get('pa', 0) + pd.get('block', 0)) / denom
        else:
            pub_fraud_rates[pub_id] = 0

    # A column: publishers with fraud >= 30%
    fraud_pubs = []
    for j, pub_id in enumerate(TARGET_PUBS):
        if pub_fraud_rates[pub_id] >= 0.3:
            fraud_pubs.append(PUB_IDS[j])
    a_val = '/'.join(fraud_pubs) + '/' if fraud_pubs else '-'

    # B column: sum of revenue for fraud publishers / 3
    fraud_rev_sum = 0
    for j, pub_id in enumerate(TARGET_PUBS):
        if pub_fraud_rates[pub_id] >= 0.3:
            fraud_rev_sum += data['pub_data'].get(pub_id, {}).get('revenue', 0)
    b_val = round(fraud_rev_sum / 3)

    # Advertiser display
    adv_name = data['parent_name']
    adv_display = adv_name  # Will be "name(id)" if needed

    row = []
    # A: 360渠道 (hardcoded value, not formula)
    row.append(a_val)
    # B: 360渠道日均收入 (hardcoded value)
    row.append(b_val)
    # C: 备注
    row.append('')
    # D: Campaign id
    row.append(int(cid))
    # E: Advertiser
    row.append(adv_display)
    # F: PackageName
    row.append(data['package_name'])
    # G: 辅助 (campaign_id)
    row.append(int(cid))
    # H: 日均收入
    daily_avg = total_rev / NUM_DAYS
    row.append(round(daily_avg, 2))
    # I: 收入
    row.append(round(total_rev, 2))
    # J: Install
    row.append(total_conv)
    # K-M: overall fraud/block/PA
    total_denom = total_block + total_conv
    if total_denom > 0:
        overall_fraud = (total_pa + total_block) / total_denom
        overall_block = total_block / total_denom
        overall_pa = total_pa / total_denom
    else:
        overall_fraud = overall_block = overall_pa = 0
    row.append(round(overall_fraud, 4))
    row.append(round(overall_block, 4))
    row.append(round(overall_pa, 4))

    # N-AQ: 10 publishers × 3 (fraud/block/PA rate as decimal)
    for pub_id in TARGET_PUBS:
        pd = data['pub_data'].get(pub_id, {})
        denom = pd.get('block', 0) + pd.get('conversions', 0)
        if denom > 0:
            fraud = (pd.get('pa', 0) + pd.get('block', 0)) / denom
            block_rate = pd.get('block', 0) / denom
            pa_rate = pd.get('pa', 0) / denom
        else:
            fraud = block_rate = pa_rate = 0
        row.append(round(fraud, 4))
        row.append(round(block_rate, 4))
        row.append(round(pa_rate, 4))

    # AR-BA: 10 publishers × revenue
    for pub_id in TARGET_PUBS:
        pd = data['pub_data'].get(pub_id, {})
        row.append(round(pd.get('revenue', 0), 2))

    output_rows.append(row)

print(f"Output rows: {len(output_rows)}")

# Step 1: Create new sheet
print("\n=== Creating sheet '0521-0524' ===")
create_url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/sheets_batch_update'
create_body = json.dumps({
    "requests": [{
        "addSheet": {
            "properties": {
                "title": "0521-0524",
                "index": 0,
                "rowCount": max(len(output_rows) + 10, 1200),
                "colCount": 53
            }
        }
    }]
}).encode()
req = urllib.request.Request(create_url, data=create_body, method='POST',
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
try:
    resp = urllib.request.urlopen(req)
    create_result = json.loads(resp.read())
    new_sheet_id = create_result['data']['replies'][0]['addSheet']['properties']['sheetId']
    print(f"Created sheet: {new_sheet_id}")
except Exception as e:
    print(f"Error creating sheet: {e}")
    # Sheet might already exist, try to find it
    new_sheet_id = None

if not new_sheet_id:
    print("Trying to find existing sheet...")
    list_url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/metainfo'
    req = urllib.request.Request(list_url, headers={'Authorization': f'Bearer {token}'})
    resp = urllib.request.urlopen(req)
    meta = json.loads(resp.read())
    for s in meta['data']['sheets']:
        if s['title'] == '0521-0524':
            new_sheet_id = s['sheetId']
            print(f"Found existing sheet: {new_sheet_id}")
            break

if not new_sheet_id:
    print("ERROR: Could not create or find sheet")
    exit(1)

SHEET = new_sheet_id
time.sleep(1)

# Step 2: Write headers
print("\n=== Writing headers ===")
headers = ['360渠道', '360渠道日均收入', '备注', 'Campaign id', 'Advertiser', 'PackageName',
           '辅助', '日均收入', '收入', 'Install',
           '整体作弊率', '整体Block率', '整体PA率']

# Add 10 publisher headers × 3
for pub_id in PUB_IDS:
    headers.extend([f'{pub_id}作弊率', f'{pub_id}Block率', f'{pub_id}PA率'])

# Add 10 publisher revenue headers
for pub_id in PUB_IDS:
    headers.append(f'{pub_id}收入')

header_row = [headers]

def api_write(range_str, values):
    url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/values'
    body = json.dumps({
        'valueRange': {
            'range': f'{SHEET}!{range_str}',
            'values': values
        }
    }).encode()
    req = urllib.request.Request(url, data=body, method='PUT',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

# Write header row
api_write('A1:BA1', header_row)
print("Headers written")
time.sleep(0.5)

# Step 3: Write summary row (row 3)
print("\n=== Writing summary row ===")
summary_row = [[''] * 53]
# I3 = SUM(I4:I{last})
last_data_row = len(output_rows) + 3
summary_row[0][8] = f'=SUM(I4:I{last_data_row})'  # I column (index 8)
summary_row[0][9] = f'=SUM(J4:J{last_data_row})'  # J column (index 9)
api_write(f'A3:BA3', summary_row)
print("Summary row written")
time.sleep(0.5)

# Step 4: Write data rows (batch of 100)
print(f"\n=== Writing {len(output_rows)} data rows ===")
BATCH = 100
for i in range(0, len(output_rows), BATCH):
    batch = output_rows[i:i+BATCH]
    rs = i + 4  # data starts at row 4
    re = rs + len(batch) - 1
    print(f"  Rows {rs}-{re} ({len(batch)} rows)")
    try:
        api_write(f'A{rs}:BA{re}', batch)
    except Exception as e:
        print(f"  Error: {e}")
    time.sleep(0.5)

# Step 5: Verify - read back first few rows
print("\n=== Verification ===")
verify_url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/values/{SHEET}!A4:BA6'
req = urllib.request.Request(verify_url, headers={'Authorization': f'Bearer {token}'})
resp = urllib.request.urlopen(req)
verify = json.loads(resp.read())
for i, row in enumerate(verify['data']['valueRange']['values']):
    print(f"  Row {i+4}: A={row[0]}, B={row[1]}, D={row[3]}, I={row[8]}, N={row[13]}")

print(f"\nDone! Sheet '{SHEET}' with {len(output_rows)} rows created.")
