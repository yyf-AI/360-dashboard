"""
360数据生成脚本 - 0525-0527
读取MCP查询结果 → 处理 → 写入飞书表格
"""
import json
import time
import os
import sys
import urllib.request
from collections import defaultdict

# ============ 配置 ============
SPREADSHEET = 'Appms4paQh298wtDRoHcmv9Gndg'
SHEET_NAME = '0525-0527'
NUM_DAYS = 3
TARGET_PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260']
PUB_IDS = ['218','220','222','223','224','226','253','254','255','260']

# ============ Feishu API ============
def load_feishu_token():
    auth_path = os.path.expanduser('~/.feishu-mcp-pro/auth.json')
    with open(auth_path, 'r') as f:
        auth = json.load(f)
    return auth['access_token']

def feishu_api(method, url, token, body=None):
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def api_write(sheet_id, range_str, values, token):
    url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/values'
    body = {'valueRange': {'range': f'{sheet_id}!{range_str}', 'values': values}}
    return feishu_api('PUT', url, token, body)

# ============ 主流程 ============
def main():
    # Step 1: Load 360 data from MCP result
    print("=== Step 1: Load 360 data ===")
    result_path = r'C:\Users\Mi\.claude\projects\C--Users-Mi\704e9fe3-fb78-4bc7-9b46-bc53494d4988\tool-results\call_f768f8e3d7cf40c794f2333e.json'
    with open(result_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    result = json.loads(raw[0]['text'])
    rows_360 = result['rows']
    print(f"  360 data: {len(rows_360)} rows")

    # Step 2: Aggregate by campaign_id
    print("\n=== Step 2: Process data ===")
    campaigns = defaultdict(lambda: {
        'revenue': 0, 'conversions': 0, 'block': 0, 'pa': 0,
        'parent_name': '', 'package_name': '', 'pub_data': {}
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

    print(f"  Unique campaigns: {len(campaigns)}")

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

        # B column: sum of revenue for fraud publishers / NUM_DAYS
        fraud_rev_sum = 0
        for j, pub_id in enumerate(TARGET_PUBS):
            if pub_fraud_rates[pub_id] >= 0.3:
                fraud_rev_sum += data['pub_data'].get(pub_id, {}).get('revenue', 0)
        b_val = round(fraud_rev_sum / NUM_DAYS)

        row = []
        row.append(a_val)                    # A: 360渠道
        row.append(b_val)                    # B: 360渠道日均收入
        row.append('')                       # C: 备注
        row.append(int(cid))                 # D: Campaign id
        row.append(data['parent_name'])      # E: Advertiser (empty - postback unavailable)
        row.append(data['package_name'])     # F: PackageName (empty - postback unavailable)
        row.append(int(cid))                 # G: 辅助
        row.append(round(total_rev / NUM_DAYS, 2))  # H: 日均收入
        row.append(round(total_rev, 2))      # I: 收入
        row.append(total_conv)               # J: Install

        # K-M: overall fraud/block/PA
        total_denom = total_block + total_conv
        if total_denom > 0:
            row.append(round((total_pa + total_block) / total_denom, 4))
            row.append(round(total_block / total_denom, 4))
            row.append(round(total_pa / total_denom, 4))
        else:
            row.extend([0, 0, 0])

        # N-AQ: 10 publishers x 3 rates
        for pub_id in TARGET_PUBS:
            pd = data['pub_data'].get(pub_id, {})
            denom = pd.get('block', 0) + pd.get('conversions', 0)
            if denom > 0:
                row.append(round((pd.get('pa', 0) + pd.get('block', 0)) / denom, 4))
                row.append(round(pd.get('block', 0) / denom, 4))
                row.append(round(pd.get('pa', 0) / denom, 4))
            else:
                row.extend([0, 0, 0])

        # AR-BA: 10 publishers x revenue
        for pub_id in TARGET_PUBS:
            pd = data['pub_data'].get(pub_id, {})
            row.append(round(pd.get('revenue', 0), 2))

        output_rows.append(row)

    print(f"  Output rows: {len(output_rows)}")
    if output_rows:
        print(f"  Columns per row: {len(output_rows[0])}")
        total_rev = sum(r[8] for r in output_rows)
        print(f"  Total revenue: ${total_rev:,.2f}")

    # Save processed data
    save_path = r'C:\Users\Mi\Desktop\processed_360_0525_0527.json'
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump({
            'target_publishers': TARGET_PUBS,
            'num_days': NUM_DAYS,
            'dates': ['20260525', '20260526', '20260527'],
            'rows': output_rows
        }, f, ensure_ascii=False)
    print(f"  Saved to {save_path}")

    # Step 3: Create new sheet
    print(f"\n=== Step 3: Create sheet '{SHEET_NAME}' ===")
    token_f = load_feishu_token()

    create_url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/sheets_batch_update'
    create_body = {
        "requests": [{
            "addSheet": {
                "properties": {
                    "title": SHEET_NAME,
                    "index": 0,
                    "rowCount": max(len(output_rows) + 10, 1200),
                    "colCount": 53
                }
            }
        }]
    }
    try:
        result = feishu_api('POST', create_url, token_f, create_body)
        new_sheet_id = result['data']['replies'][0]['addSheet']['properties']['sheetId']
        print(f"  Created sheet: {new_sheet_id}")
    except Exception as e:
        print(f"  Error creating sheet: {e}")
        meta_url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/metainfo'
        meta = feishu_api('GET', meta_url, token_f)
        new_sheet_id = None
        for s in meta['data']['sheets']:
            if s['title'] == SHEET_NAME:
                new_sheet_id = s['sheetId']
                break
        if not new_sheet_id:
            print("  FATAL: Cannot create sheet")
            sys.exit(1)
        print(f"  Found existing sheet: {new_sheet_id}")

    SHEET = new_sheet_id
    time.sleep(1)

    # Step 4: Write headers
    print("\n=== Step 4: Write headers ===")
    headers = ['360渠道', '360渠道日均收入', '备注', 'Campaign id', 'Advertiser', 'PackageName',
               '辅助', '日均收入', '收入', 'Install',
               '整体作弊率', '整体Block率', '整体PA率']
    for pub_id in PUB_IDS:
        headers.extend([f'{pub_id}作弊率', f'{pub_id}Block率', f'{pub_id}PA率'])
    for pub_id in PUB_IDS:
        headers.append(f'{pub_id}收入')

    api_write(SHEET, 'A1:BA1', [headers], token_f)
    print("  Headers written")
    time.sleep(0.5)

    # Step 5: Write summary row (row 3)
    print("\n=== Step 5: Write summary row ===")
    total_revenue = sum(r[8] for r in output_rows)
    total_installs = sum(r[9] for r in output_rows)
    total_fraud_rev = sum(r[1] for r in output_rows)

    summary_row = [''] * 53
    summary_row[1] = round(total_fraud_rev / NUM_DAYS) if output_rows else 0  # B
    summary_row[7] = round(total_revenue / NUM_DAYS, 2)  # H
    summary_row[8] = round(total_revenue, 2)  # I
    summary_row[9] = total_installs  # J
    api_write(SHEET, 'A3:BA3', [summary_row], token_f)
    print("  Summary row written")
    time.sleep(0.5)

    # Step 6: Write data rows (batch of 100)
    print(f"\n=== Step 6: Write {len(output_rows)} data rows ===")
    BATCH = 100
    for i in range(0, len(output_rows), BATCH):
        batch = output_rows[i:i+BATCH]
        rs = i + 4
        re = rs + len(batch) - 1
        print(f"  Rows {rs}-{re} ({len(batch)} rows)")
        try:
            api_write(SHEET, f'A{rs}:BA{re}', batch, token_f)
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(0.5)

    # Step 7: Apply formatting
    print("\n=== Step 7: Apply formatting ===")
    style_url = f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/styles_batch_update'

    # Header style
    try:
        feishu_api('POST', style_url, token_f, {
            "data": [{"ranges": f"{SHEET}!A1:BA1", "style": {"backColor": "#F3C21B", "bold": True, "hAlign": 0}}]
        })
        print("  Header style applied")
    except Exception as e:
        print(f"  Header style error: {e}")
    time.sleep(0.5)

    # Summary row style
    try:
        feishu_api('POST', style_url, token_f, {
            "data": [{"ranges": f"{SHEET}!A3:BA3", "style": {"backColor": "#E8EAED", "bold": True}}]
        })
        print("  Summary row style applied")
    except Exception as e:
        print(f"  Summary style error: {e}")
    time.sleep(0.5)

    # Number formats
    last_row = len(output_rows) + 3
    try:
        feishu_api('POST', style_url, token_f, {
            "data": [
                {"ranges": f"{SHEET}!H4:H{last_row}", "style": {"formatter": "#,##0.00"}},
                {"ranges": f"{SHEET}!I4:I{last_row}", "style": {"formatter": "#,##0.00"}},
                {"ranges": f"{SHEET}!AR4:BA{last_row}", "style": {"formatter": "#,##0.00"}},
                {"ranges": f"{SHEET}!B4:B{last_row}", "style": {"formatter": "#,##0"}},
                {"ranges": f"{SHEET}!K4:AQ{last_row}", "style": {"formatter": "0.00%"}}
            ]
        })
        print("  Number formats applied")
    except Exception as e:
        print(f"  Format error: {e}")

    # Freeze rows
    try:
        feishu_api('PUT',
            f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/sheets/{SHEET}/freeze',
            token_f, {"freezePane": {"freezeRow": 3}})
        print("  Frozen rows applied")
    except Exception as e:
        print(f"  Freeze error: {e}")

    # Step 8: Verify
    print("\n=== Step 8: Verify ===")
    verify = feishu_api('GET',
        f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{SPREADSHEET}/values/{SHEET}!A4:BA6',
        token_f)
    for i, row in enumerate(verify['data']['valueRange']['values']):
        print(f"  Row {i+4}: A={row[0]}, B={row[1]}, D={row[3]}, I={row[8]}, K={row[10]}")

    print(f"\n✅ Done! Sheet '{SHEET_NAME}' with {len(output_rows)} rows created.")
    print(f"   Total revenue: ${total_revenue:,.2f}")
    print(f"   Total installs: {total_installs:,}")
    print(f"   Daily average: ${total_revenue/NUM_DAYS:,.2f}")

if __name__ == '__main__':
    main()
