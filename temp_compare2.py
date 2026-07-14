import json, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\Mi\.claude\projects\C--Users-Mi\a90c26ca-25a4-4742-9aba-a0eb1567530f\tool-results\call_8796ad50f1754e11b53ab2fe.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

result = json.loads(data[0]['text'])
columns = [c['name'] for c in result['columns']]
rows = result['rows']

# Aggregate by campaign_id + date
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

# Compare 0709 vs 0710
results = []
for cid in sorted(agg.keys()):
    d9 = agg[cid].get(20260709, {'rev':0,'conv':0,'payout':0,'post_conv':0,'campaign_name':''})
    d10 = agg[cid].get(20260710, {'rev':0,'conv':0,'payout':0,'post_conv':0,'campaign_name':''})
    cname = d9['campaign_name'] or d10['campaign_name']
    gap = d10['rev'] - d9['rev']
    pct = (gap / d9['rev'] * 100) if d9['rev'] > 0 else 0
    results.append({
        'cid': cid, 'cname': cname,
        'r9': d9['rev'], 'r10': d10['rev'], 'gap': gap, 'pct': pct,
        'c9': d9['conv'], 'c10': d10['conv'],
        'p9': d9['payout'], 'p10': d10['payout'],
        'pc9': d9['post_conv'], 'pc10': d10['post_conv'],
    })

results.sort(key=lambda x: x['gap'])

total_r9 = sum(r['r9'] for r in results)
total_r10 = sum(r['r10'] for r in results)
total_gap = total_r10 - total_r9

print(f'com.netease.newspike  0709总: ${total_r9:,.2f}  0710总: ${total_r10:,.2f}  gap: ${total_gap:+,.2f} ({total_gap/total_r9*100:+.1f}%)')
print()
print(f'{"Campaign":>12s}  {"Campaign名称":30s}  {"0709收入":>10s}  {"0710收入":>10s}  {"gap":>10s}  {"幅度":>8s}  {"0709转化":>8s}  {"0710转化":>8s}  {"0709回传":>8s}  {"0710回传":>8s}')
print('-' * 130)
for r in results:
    print(f'{r["cid"]:>12s}  {r["cname"]:30s}  ${r["r9"]:>9,.2f}  ${r["r10"]:>9,.2f}  ${r["gap"]:>+9,.2f}  {r["pct"]:>+7.1f}%  {r["c9"]:>8,}  {r["c10"]:>8,}  {r["pc9"]:>8,}  {r["pc10"]:>8,}')
