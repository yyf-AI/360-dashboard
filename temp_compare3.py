import json, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\Mi\.claude\projects\C--Users-Mi\a90c26ca-25a4-4742-9aba-a0eb1567530f\tool-results\call_ddfa2d33b01640b094f95d7b.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

result = json.loads(data[0]['text'])
columns = [c['name'] for c in result['columns']]
rows = result['rows']

agg = defaultdict(lambda: defaultdict(lambda: {'rev':0, 'conv':0, 'payout':0, 'post_conv':0, 'campaign_name':''}))
for row in rows:
    d = dict(zip(columns, row))
    cid = str(d['campaign_id'])
    dt = d['date']
    agg[cid][dt]['rev'] += d['revenue'] or 0
    agg[cid][dt]['conv'] += d['conversions'] or 0
    agg[cid][dt]['payout'] += d['payout'] or 0
    agg[cid][dt]['post_conv'] += d['post_conversions'] or 0
    agg[cid][dt]['campaign_name'] = d['campaign_name'] or ''

results = []
for cid in sorted(agg.keys()):
    d12 = agg[cid].get(20260712, {'rev':0,'conv':0,'payout':0,'post_conv':0,'campaign_name':''})
    d13 = agg[cid].get(20260713, {'rev':0,'conv':0,'payout':0,'post_conv':0,'campaign_name':''})
    cname = d12['campaign_name'] or d13['campaign_name']
    gap = d13['rev'] - d12['rev']
    pct = (gap / d12['rev'] * 100) if d12['rev'] > 0 else 0
    results.append({
        'cid': cid, 'cname': cname,
        'r12': d12['rev'], 'r13': d13['rev'], 'gap': gap, 'pct': pct,
        'c12': d12['conv'], 'c13': d13['conv'],
        'pc12': d12['post_conv'], 'pc13': d13['post_conv'],
    })

results.sort(key=lambda x: x['gap'])

total_r12 = sum(r['r12'] for r in results)
total_r13 = sum(r['r13'] for r in results)
total_gap = total_r13 - total_r12

print(f'com.netease.newspike  0712总: ${total_r12:,.2f}  0713总: ${total_r13:,.2f}  gap: ${total_gap:+,.2f} ({total_gap/total_r12*100:+.1f}%)')
print()
print(f'{"Campaign":>12s}  {"国家":8s}  {"0712收入":>10s}  {"0713收入":>10s}  {"gap":>10s}  {"幅度":>8s}  {"0712转化":>8s}  {"0713转化":>8s}  {"0712回传":>8s}  {"0713回传":>8s}')
print('-' * 120)
for r in results:
    country = r['cname'].replace('recl-netease-','') if r['cname'] else '-'
    print(f'{r["cid"]:>12s}  {country:8s}  ${r["r12"]:>9,.2f}  ${r["r13"]:>9,.2f}  ${r["gap"]:>+9,.2f}  {r["pct"]:>+7.1f}%  {r["c12"]:>8,}  {r["c13"]:>8,}  {r["pc12"]:>8,}  {r["pc13"]:>8,}')
