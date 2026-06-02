import json

RESULT_PATH = r"C:\Users\Mi\.claude\projects\C--Users-Mi\1019789b-31f3-47ee-9d87-5be59be0d64e\tool-results\call_910df5b406ce456bb8fe5057.json"
WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/8843f281-2440-4f13-a75f-4ef0e7a815d4"

TARGET_PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260']

with open(RESULT_PATH, 'r', encoding='utf-8') as f:
    raw = json.load(f)
result = json.loads(raw[0]['text'])
rows = result['rows']

# Filter 0524 only
from collections import defaultdict
campaigns = defaultdict(lambda: {
    'revenue': 0, 'conversions': 0, 'block': 0, 'pa': 0,
    'parent_name': '', 'package_name': '',
    'pub_fraud': {}, 'pub_rev': {}
})

for row in rows:
    date, cid, parent_name, pkg, pub_id, rev, conv, block, pa = row
    if str(date) != '20260524':
        continue

    campaigns[cid]['revenue'] += rev
    campaigns[cid]['conversions'] += conv
    campaigns[cid]['block'] += block
    campaigns[cid]['pa'] += pa
    if parent_name:
        campaigns[cid]['parent_name'] = parent_name
    if pkg:
        campaigns[cid]['package_name'] = pkg

    total_denom = block + conv
    fraud = (pa + block) / total_denom if total_denom > 0 else 0
    campaigns[cid]['pub_fraud'][pub_id] = round(fraud, 4)
    campaigns[cid]['pub_rev'][pub_id] = round(rev, 2)

# Filter: revenue >= 100 and overall fraud > 20%
alerts = []
for cid, data in campaigns.items():
    total_denom = data['block'] + data['conversions']
    if total_denom <= 0:
        continue
    overall_fraud = (data['pa'] + data['block']) / total_denom
    if data['revenue'] >= 100 and overall_fraud > 0.2:
        # Find high-fraud publishers
        high_fraud_pubs = []
        for pub_id in TARGET_PUBS:
            pf = data['pub_fraud'].get(pub_id, 0)
            pr = data['pub_rev'].get(pub_id, 0)
            if pf > 0.2 and pr > 10:
                high_fraud_pubs.append((pub_id, pf, pr))
        high_fraud_pubs.sort(key=lambda x: -x[2])

        alerts.append({
            'campaign_id': cid,
            'advertiser': data['parent_name'],
            'package_name': data['package_name'],
            'revenue': round(data['revenue'], 2),
            'overall_fraud': round(overall_fraud * 100, 2),
            'high_fraud_pubs': high_fraud_pubs
        })

alerts.sort(key=lambda x: -x['revenue'])
print(f"Found {len(alerts)} campaigns with revenue≥$100 and fraud>20%")

if not alerts:
    print("No alerts to send")
    exit()

# Build message
lines = []
lines.append("360高收入高作弊渠道告警 (0524)")
lines.append(f"共 {len(alerts)} 个campaign触发告警")
lines.append("")

for a in alerts[:30]:  # Top 30
    adv = a['advertiser'] or ''
    pkg = a['package_name'] or ''
    cid = a['campaign_id']
    rev = a['revenue']
    fraud = a['overall_fraud']

    header = f"[{pkg}] {adv}({cid})  收入${rev:,.0f}  作弊率{fraud}%"
    lines.append(header)

    for pub_id, pf, pr in a['high_fraud_pubs']:
        lines.append(f"  渠道{pub_id}: 作弊率{pf*100:.1f}%  收入${pr:,.0f}")

# Send to Feishu
import urllib.request

post_content = []
for line in lines:
    post_content.append([{"tag": "text", "text": line}])

payload = {
    "msg_type": "post",
    "content": {
        "post": {
            "zh_cn": {
                "title": f"360高作弊告警 (0524) - {len(alerts)}个campaign",
                "content": post_content
            }
        }
    }
}

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(WEBHOOK, data=data,
    headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
print(f"Feishu response: {result}")
