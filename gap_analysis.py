"""
0526 vs 0527 GAP分析: 点击(AF) + 收入/激活(postback)
维度: 包名, Publisher, Advertiser
"""
import json, sys, io
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# === Load AF data (per-day) ===
AF_DIR = Path(r"C:\Users\Mi\360_dashboard")

def load_af_day(date_str):
    """Load AF data for a single day. date_str like '20260526'"""
    fpath = AF_DIR / f"af_data_{date_str}_{date_str}.json"
    if not fpath.exists():
        print(f"[WARN] AF data not found: {fpath}")
        return {}
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)

# === Load postback data ===
POSTBACK_FILE = Path(r"C:\Users\Mi\.claude\projects\C--Users-Mi\1019789b-31f3-47ee-9d87-5be59be0d64e\tool-results\call_ed069b49e5514c1b931dc279.json")

def load_postback():
    with open(POSTBACK_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    result = json.loads(raw[0]['text'])
    return result['rows']

def fp(p):
    return "NEW" if abs(p) >= 10000 else f"{p:+.1f}%"

def fp2(p):
    """Format percentage for display"""
    if abs(p) >= 10000:
        return "NEW"
    return f"{p:+.1f}%"

def main():
    # Load data
    af_26 = load_af_day("20260526")
    af_27 = load_af_day("20260527")
    postback_rows = load_postback()

    print(f"AF 0526: {len(af_26)} packages ({sum(1 for v in af_26.values() if v)} with data)")
    print(f"AF 0527: {len(af_27)} packages ({sum(1 for v in af_27.values() if v)} with data)")
    print(f"Postback: {len(postback_rows)} rows\n")

    # === Aggregate AF data by package ===
    # af_day[pkg] = {clicks, installs, revenue}
    def aggregate_af(day_data):
        result = {}
        for pkg, adsets in day_data.items():
            if not adsets:
                continue
            clicks = sum(a.get("clicks", 0) or 0 for a in adsets.values())
            installs = sum(a.get("installs", 0) or 0 for a in adsets.values())
            revenue = sum(a.get("revenue", 0) or 0 for a in adsets.values())
            result[pkg] = {"clicks": clicks, "installs": installs, "revenue": revenue}
        return result

    af_agg_26 = aggregate_af(af_26)
    af_agg_27 = aggregate_af(af_27)

    # === Aggregate AF data by package+publisher (adset) ===
    def aggregate_af_by_pub(day_data):
        result = defaultdict(lambda: {"clicks": 0, "installs": 0, "revenue": 0})
        for pkg, adsets in day_data.items():
            for adset, vals in adsets.items():
                key = (pkg, adset)
                result[key]["clicks"] += vals.get("clicks", 0) or 0
                result[key]["installs"] += vals.get("installs", 0) or 0
                result[key]["revenue"] += vals.get("revenue", 0) or 0
        return dict(result)

    af_pub_26 = aggregate_af_by_pub(af_26)
    af_pub_27 = aggregate_af_by_pub(af_27)

    # === Aggregate postback data ===
    # postback: package_name, advertiser_name, advertiser_id, publisher_id, rev_0527, rev_0526, conv_0527, conv_0526
    postback_pkg = defaultdict(lambda: {"r26": 0, "r27": 0, "c26": 0, "c27": 0})
    postback_pub = defaultdict(lambda: {"r26": 0, "r27": 0, "c26": 0, "c27": 0})
    postback_adv = defaultdict(lambda: {"r26": 0, "r27": 0, "c26": 0, "c27": 0})

    for row in postback_rows:
        pkg = row[0] or '(empty)'
        adv_name = row[1] or ''
        adv_id = row[2] or ''
        pub_id = str(row[3]) if row[3] else '(empty)'
        rev_27 = row[4] or 0
        rev_26 = row[5] or 0
        conv_27 = row[6] or 0
        conv_26 = row[7] or 0

        adv_key = f"{adv_name}({adv_id})" if adv_name and adv_id else (adv_name or str(adv_id) or '(empty)')

        for d in [postback_pkg[pkg], postback_pub[pub_id], postback_adv[adv_key]]:
            d['r26'] += rev_26; d['r27'] += rev_27
            d['c26'] += conv_26; d['c27'] += conv_27

    # === Build combined metrics ===
    # pkg_metrics[pkg] = {clicks_26, clicks_27, installs_26, installs_27, revenue_26, revenue_27, conv_26, conv_27}
    all_pkgs = set(list(af_agg_26.keys()) + list(af_agg_27.keys()) + list(postback_pkg.keys()))
    pkg_metrics = {}
    for pkg in all_pkgs:
        af26 = af_agg_26.get(pkg, {"clicks": 0, "installs": 0, "revenue": 0})
        af27 = af_agg_27.get(pkg, {"clicks": 0, "installs": 0, "revenue": 0})
        pb = postback_pkg.get(pkg, {"r26": 0, "r27": 0, "c26": 0, "c27": 0})
        pkg_metrics[pkg] = {
            "clicks_26": af26["clicks"], "clicks_27": af27["clicks"],
            "installs_26": af26["installs"], "installs_27": af27["installs"],
            "af_rev_26": af26["revenue"], "af_rev_27": af27["revenue"],
            "rev_26": pb["r26"], "rev_27": pb["r27"],
            "conv_26": pb["c26"], "conv_27": pb["c27"],
        }

    # === Publisher combined (aggregate AF by adset only) ===
    af_pubonly_26 = defaultdict(lambda: {"clicks": 0, "installs": 0, "revenue": 0})
    af_pubonly_27 = defaultdict(lambda: {"clicks": 0, "installs": 0, "revenue": 0})
    for (pkg, adset), vals in af_pub_26.items():
        for k in ["clicks", "installs", "revenue"]:
            af_pubonly_26[adset][k] += vals.get(k, 0)
    for (pkg, adset), vals in af_pub_27.items():
        for k in ["clicks", "installs", "revenue"]:
            af_pubonly_27[adset][k] += vals.get(k, 0)

    all_pubs = set(list(af_pubonly_26.keys()) + list(af_pubonly_27.keys()) + list(postback_pub.keys()))
    pub_metrics = {}
    for pub in all_pubs:
        af26 = af_pubonly_26.get(pub, {"clicks": 0, "installs": 0, "revenue": 0})
        af27 = af_pubonly_27.get(pub, {"clicks": 0, "installs": 0, "revenue": 0})
        pb = postback_pub.get(pub, {"r26": 0, "r27": 0, "c26": 0, "c27": 0})
        pub_metrics[pub] = {
            "clicks_26": af26["clicks"], "clicks_27": af27["clicks"],
            "installs_26": af26["installs"], "installs_27": af27["installs"],
            "af_rev_26": af26["revenue"], "af_rev_27": af27["revenue"],
            "rev_26": pb["r26"], "rev_27": pb["r27"],
            "conv_26": pb["c26"], "conv_27": pb["c27"],
        }

    # === Calculate drops ===
    def calc_drops(data_dict, key_gap, key_base):
        drops = []
        for name, d in data_dict.items():
            gap = d[key_gap] - d[key_base]
            pct = gap / d[key_base] * 100 if d[key_base] > 0 else (0 if gap == 0 else float('inf'))
            drops.append((name, d, gap, pct))
        drops.sort(key=lambda x: x[2])
        return drops

    # === OUTPUT ===
    print("=" * 140)
    print("TOP 20 包名 — 收入下降最多 (0526 → 0527)  [收入来自Postback]")
    print("=" * 140)
    print(f"{'包名':<45} {'0526收入':>10} {'0527收入':>10} {'收入GAP':>10} {'GAP%':>8}  {'0526点击':>10} {'0527点击':>10} {'点击GAP':>10}  {'0526激活':>8} {'0527激活':>8} {'激活GAP':>8}")
    for name, d, gap, pct in calc_drops(pkg_metrics, 'rev_27', 'rev_26')[:20]:
        cg = d['clicks_27'] - d['clicks_26']
        ig = d['conv_27'] - d['conv_26']
        print(f"{name[:45]:<45} {d['rev_26']:>10,.0f} {d['rev_27']:>10,.0f} {gap:>10,.0f} {fp2(pct):>8}  {d['clicks_26']:>10,} {d['clicks_27']:>10,} {cg:>10,}  {d['conv_26']:>8,} {d['conv_27']:>8,} {ig:>8,}")

    print("\n" + "=" * 140)
    print("TOP 20 包名 — 点击下降最多 (0526 → 0527)  [点击来自AF]")
    print("=" * 140)
    print(f"{'包名':<45} {'0526点击':>10} {'0527点击':>10} {'点击GAP':>10} {'GAP%':>8}  {'0526收入':>10} {'0527收入':>10} {'收入GAP':>10}  {'0526激活':>8} {'0527激活':>8} {'激活GAP':>8}")
    for name, d, gap, pct in calc_drops(pkg_metrics, 'clicks_27', 'clicks_26')[:20]:
        rg = d['rev_27'] - d['rev_26']
        ig = d['conv_27'] - d['conv_26']
        print(f"{name[:45]:<45} {d['clicks_26']:>10,} {d['clicks_27']:>10,} {gap:>10,} {fp2(pct):>8}  {d['rev_26']:>10,.0f} {d['rev_27']:>10,.0f} {rg:>10,.0f}  {d['conv_26']:>8,} {d['conv_27']:>8,} {ig:>8,}")

    print("\n" + "=" * 140)
    print("TOP 20 Publisher — 收入下降最多 (0526 → 0527)  [收入来自Postback]")
    print("=" * 140)
    print(f"{'Publisher':<12} {'0526收入':>10} {'0527收入':>10} {'收入GAP':>10} {'GAP%':>8}  {'0526点击':>10} {'0527点击':>10} {'点击GAP':>10}  {'0526激活':>8} {'0527激活':>8} {'激活GAP':>8}")
    for name, d, gap, pct in calc_drops(pub_metrics, 'rev_27', 'rev_26')[:20]:
        cg = d['clicks_27'] - d['clicks_26']
        ig = d['conv_27'] - d['conv_26']
        print(f"{name:<12} {d['rev_26']:>10,.0f} {d['rev_27']:>10,.0f} {gap:>10,.0f} {fp2(pct):>8}  {d['clicks_26']:>10,} {d['clicks_27']:>10,} {cg:>10,}  {d['conv_26']:>8,} {d['conv_27']:>8,} {ig:>8,}")

    print("\n" + "=" * 140)
    print("TOP 20 Publisher — 点击下降最多 (0526 → 0527)  [点击来自AF]")
    print("=" * 140)
    print(f"{'Publisher':<12} {'0526点击':>10} {'0527点击':>10} {'点击GAP':>10} {'GAP%':>8}  {'0526收入':>10} {'0527收入':>10} {'收入GAP':>10}  {'0526激活':>8} {'0527激活':>8} {'激活GAP':>8}")
    for name, d, gap, pct in calc_drops(pub_metrics, 'clicks_27', 'clicks_26')[:20]:
        rg = d['rev_27'] - d['rev_26']
        ig = d['conv_27'] - d['conv_26']
        print(f"{name:<12} {d['clicks_26']:>10,} {d['clicks_27']:>10,} {gap:>10,} {fp2(pct):>8}  {d['rev_26']:>10,.0f} {d['rev_27']:>10,.0f} {rg:>10,.0f}  {d['conv_26']:>8,} {d['conv_27']:>8,} {ig:>8,}")

    print("\n" + "=" * 140)
    print("TOP 20 Advertiser — 收入下降最多 (0526 → 0527)  [收入来自Postback]")
    print("=" * 140)
    print(f"{'Advertiser':<50} {'0526收入':>10} {'0527收入':>10} {'收入GAP':>10} {'GAP%':>8}  {'0526激活':>8} {'0527激活':>8} {'激活GAP':>8}")
    for name, d, gap, pct in calc_drops(postback_adv, 'r27', 'r26')[:20]:
        ig = d['c27'] - d['c26']
        print(f"{name[:50]:<50} {d['r26']:>10,.0f} {d['r27']:>10,.0f} {gap:>10,.0f} {fp2(pct):>8}  {d['c26']:>8,} {d['c27']:>8,} {ig:>8,}")

    # === Overall ===
    t_pb = lambda k: sum(d[k] for d in postback_pkg.values())
    t_af_26 = lambda k: sum(d[k] for d in af_agg_26.values())
    t_af_27 = lambda k: sum(d[k] for d in af_agg_27.values())

    print("\n" + "=" * 140)
    print("总体对比")
    print("=" * 140)
    r26, r27 = t_pb('r26'), t_pb('r27')
    c26, c27 = t_pb('c26'), t_pb('c27')
    cl26 = t_af_26('clicks')
    cl27 = t_af_27('clicks')
    in26 = t_af_26('installs')
    in27 = t_af_27('installs')
    print(f"收入(Postback): ${r26:,.0f} → ${r27:,.0f} (GAP: ${r27-r26:,.0f}, {(r27-r26)/r26*100:+.1f}%)")
    print(f"激活(Postback): {c26:,} → {c27:,} (GAP: {c27-c26:,}, {(c27-c26)/c26*100:+.1f}%)")
    print(f"点击(AF):      {cl26:,} → {cl27:,} (GAP: {cl27-cl26:,}, {(cl27-cl26)/cl26*100:+.1f}%)")
    print(f"安装(AF):      {in26:,} → {in27:,} (GAP: {in27-in26:,}, {(in27-in26)/in26*100:+.1f}%)")


if __name__ == "__main__":
    main()
