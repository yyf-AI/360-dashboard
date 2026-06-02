import json, sys, io
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r"C:\Users\Mi\.claude\projects\C--Users-Mi\1019789b-31f3-47ee-9d87-5be59be0d64e\tool-results\call_ed069b49e5514c1b931dc279.json", "r", encoding="utf-8") as f:
    raw = json.load(f)

result = json.loads(raw[0]['text'])
rows = result['rows']
print(f"Total rows: {len(rows)}")

# Columns: package_name[0], advertiser_name[1], advertiser_id[2], publisher_id[3],
#           rev_0527[4], rev_0526[5], conv_0527[6], conv_0526[7]

def make_adv(row):
    name = row[1] or ''
    aid = row[2] or ''
    return f"{name}({aid})" if name and aid else (name or str(aid) or '(empty)')

def make_pub(row):
    return str(row[3]) if row[3] else '(empty)'

# Aggregate
keys = ['r27', 'r26', 'c27', 'c26']
pkg_data = defaultdict(lambda: {k: 0 for k in keys})
pub_data = defaultdict(lambda: {k: 0 for k in keys})
adv_data = defaultdict(lambda: {k: 0 for k in keys})

for row in rows:
    pkg = row[0] or '(empty)'
    adv = make_adv(row)
    pub = make_pub(row)
    r27, r26 = row[4] or 0, row[5] or 0
    c27, c26 = row[6] or 0, row[7] or 0

    for d in [pkg_data[pkg], pub_data[pub], adv_data[adv]]:
        d['r27'] += r27; d['r26'] += r26
        d['c27'] += c27; d['c26'] += c26

def calc_drops(data_dict):
    drops = []
    for name, d in data_dict.items():
        rgap = d['r27'] - d['r26']
        rpct = rgap / d['r26'] * 100 if d['r26'] > 0 else (0 if rgap == 0 else float('inf'))
        cgap = d['c27'] - d['c26']
        drops.append((name, d['r26'], d['r27'], rgap, rpct, d['c26'], d['c27'], cgap))
    drops.sort(key=lambda x: x[3])
    return drops

def fp(p):
    return "NEW" if abs(p) >= 10000 else f"{p:+.1f}%"

# === Package drops ===
print("\n" + "="*115)
print("TOP 15 包名 — 收入下降最多 (0526 → 0527)")
print("="*115)
print(f"{'包名':<45} {'0526收入':>10} {'0527收入':>10} {'收入GAP':>10} {'GAP%':>7}  {'0526激活':>8} {'0527激活':>8} {'激活GAP':>8}")
for name, r26, r27, rg, rp, c26, c27, cg in calc_drops(pkg_data)[:15]:
    print(f"{name[:45]:<45} {r26:>10,.0f} {r27:>10,.0f} {rg:>10,.0f} {fp(rp):>7}  {c26:>8,} {c27:>8,} {cg:>8,}")

# === Publisher drops ===
print("\n" + "="*115)
print("TOP 15 Publisher — 收入下降最多 (0526 → 0527)")
print("="*115)
print(f"{'Publisher':<12} {'0526收入':>10} {'0527收入':>10} {'收入GAP':>10} {'GAP%':>7}  {'0526激活':>8} {'0527激活':>8} {'激活GAP':>8}")
for name, r26, r27, rg, rp, c26, c27, cg in calc_drops(pub_data)[:15]:
    print(f"{name:<12} {r26:>10,.0f} {r27:>10,.0f} {rg:>10,.0f} {fp(rp):>7}  {c26:>8,} {c27:>8,} {cg:>8,}")

# === Advertiser drops ===
print("\n" + "="*115)
print("TOP 15 Advertiser — 收入下降最多 (0526 → 0527)")
print("="*115)
print(f"{'Advertiser':<50} {'0526收入':>10} {'0527收入':>10} {'收入GAP':>10} {'GAP%':>7}  {'0526激活':>8} {'0527激活':>8} {'激活GAP':>8}")
for name, r26, r27, rg, rp, c26, c27, cg in calc_drops(adv_data)[:15]:
    print(f"{name[:50]:<50} {r26:>10,.0f} {r27:>10,.0f} {rg:>10,.0f} {fp(rp):>7}  {c26:>8,} {c27:>8,} {cg:>8,}")

# === Overall ===
t = lambda k: sum(d[k] for d in pkg_data.values())
print("\n" + "="*115)
print("总体对比")
print("="*115)
r26, r27 = t('r26'), t('r27')
c26, c27 = t('c26'), t('c27')
print(f"收入: ${r26:,.0f} → ${r27:,.0f} (GAP: ${r27-r26:,.0f}, {(r27-r26)/r26*100:+.1f}%)")
print(f"激活: {c26:,} → {c27:,} (GAP: {c27-c26:,}, {(c27-c26)/c26*100:+.1f}%)")
