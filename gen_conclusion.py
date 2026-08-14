import pandas as pd

df = pd.read_csv(r'C:\Users\Mi\Downloads\report_export - 2026-08-14T170947.636.csv')

for col in ['clicks', 'revenue', 'payout', 'profit', 'conversions', 'postback_conversions']:
    df[col] = df[col].astype(str).str.replace(',', '').astype(float)

df = df.rename(columns={
    'groupby_1': 'date', 'groupby_2': 'package_name',
    'groupby_3': 'advertiser', 'groupby_4': 'extra'
})

def date_sort_key(d):
    parts = d.split('/')
    return int(parts[0]) * 10000 + int(parts[1]) * 100 + int(parts[2])

dates = sorted(df['date'].unique(), key=date_sort_key)
latest = dates[-1]
prev = dates[-2]

# 按广告主+包名+日期汇总
adv_pkg = df.groupby(['advertiser', 'package_name', 'date']).agg({
    'clicks': 'sum', 'revenue': 'sum', 'conversions': 'sum'
}).reset_index()

# 按广告主+日期汇总
adv_daily = df.groupby(['advertiser', 'date']).agg({
    'clicks': 'sum', 'revenue': 'sum', 'conversions': 'sum'
}).reset_index()

results = []

for adv in adv_daily['advertiser'].unique():
    adv_data = adv_daily[adv_daily['advertiser'] == adv]
    latest_row = adv_data[adv_data['date'] == latest]
    prev_row = adv_data[adv_data['date'] == prev]

    if len(latest_row) == 0 or len(prev_row) == 0:
        continue

    rev_now = latest_row['revenue'].values[0]
    rev_prev = prev_row['revenue'].values[0]
    clicks_now = latest_row['clicks'].values[0]
    clicks_prev = prev_row['clicks'].values[0]
    rev_change = rev_now - rev_prev
    clicks_change = clicks_now - clicks_prev
    rev_pct = (rev_change / rev_prev * 100) if rev_prev > 0 else 0
    clicks_pct = (clicks_change / clicks_prev * 100) if clicks_prev > 0 else 0

    # 找出收入变化最大的包
    adv_pkgs = adv_pkg[adv_pkg['advertiser'] == adv]
    pkg_impact = []

    for pkg in adv_pkgs['package_name'].unique():
        pkg_data = adv_pkgs[adv_pkgs['package_name'] == pkg]
        pkg_latest = pkg_data[pkg_data['date'] == latest]
        pkg_prev = pkg_data[pkg_data['date'] == prev]

        pkg_rev_now = pkg_latest['revenue'].values[0] if len(pkg_latest) > 0 else 0
        pkg_rev_prev = pkg_prev['revenue'].values[0] if len(pkg_prev) > 0 else 0
        pkg_clicks_now = pkg_latest['clicks'].values[0] if len(pkg_latest) > 0 else 0
        pkg_clicks_prev = pkg_prev['clicks'].values[0] if len(pkg_prev) > 0 else 0
        pkg_rev_diff = pkg_rev_now - pkg_rev_prev
        pkg_clicks_diff = pkg_clicks_now - pkg_clicks_prev

        if abs(pkg_rev_diff) > 5 or abs(pkg_clicks_diff) > 5000:
            pkg_impact.append({
                'pkg': pkg,
                'rev_diff': pkg_rev_diff,
                'clicks_diff': pkg_clicks_diff,
                'rev_now': pkg_rev_now,
                'rev_prev': pkg_rev_prev
            })

    pkg_impact.sort(key=lambda x: abs(x['rev_diff']), reverse=True)

    results.append({
        'advertiser': adv,
        'rev_now': rev_now,
        'rev_prev': rev_prev,
        'rev_change': rev_change,
        'rev_pct': rev_pct,
        'clicks_now': clicks_now,
        'clicks_prev': clicks_prev,
        'clicks_change': clicks_change,
        'clicks_pct': clicks_pct,
        'pkg_impact': pkg_impact[:5]
    })

results.sort(key=lambda x: x['rev_change'])

# 生成结论文本
lines = []
lines.append("=" * 80)
lines.append(f"Advertiser数据变化结论总结（{prev} vs {latest}）")
lines.append("=" * 80)

# 下滑的
down = [r for r in results if r['rev_change'] < -50]
up = [r for r in results if r['rev_change'] > 50]
flat = [r for r in results if -50 <= r['rev_change'] <= 50]

lines.append(f"\n📊 整体概览: 共{len(results)}个广告主, 下滑{len(down)}个, 增长{len(up)}个, 持平{len(flat)}个")

if down:
    lines.append(f"\n{'─' * 80}")
    lines.append("📉 收入下滑广告主")
    lines.append(f"{'─' * 80}")
    for r in down:
        lines.append(f"\n▶ {r['advertiser']}")
        lines.append(f"  收入: ${r['rev_prev']:,.2f} → ${r['rev_now']:,.2f} ({r['rev_change']:+,.2f}, {r['rev_pct']:+.1f}%)")
        lines.append(f"  点击: {r['clicks_prev']:,.0f} → {r['clicks_now']:,.0f} ({r['clicks_change']:+,.0f}, {r['clicks_pct']:+.1f}%)")
        if r['pkg_impact']:
            lines.append(f"  主要影响包:")
            for p in r['pkg_impact'][:3]:
                if abs(p['rev_diff']) < 5:
                    continue
                pkg_dir = "↑" if p['rev_diff'] > 0 else "↓"
                lines.append(f"    {pkg_dir} {p['pkg'][:50]}: ${p['rev_prev']:,.2f}→${p['rev_now']:,.2f} ({p['rev_diff']:+,.2f})")

if up:
    lines.append(f"\n{'─' * 80}")
    lines.append("📈 收入增长广告主")
    lines.append(f"{'─' * 80}")
    for r in up:
        lines.append(f"\n▶ {r['advertiser']}")
        lines.append(f"  收入: ${r['rev_prev']:,.2f} → ${r['rev_now']:,.2f} ({r['rev_change']:+,.2f}, {r['rev_pct']:+.1f}%)")
        lines.append(f"  点击: {r['clicks_prev']:,.0f} → {r['clicks_now']:,.0f} ({r['clicks_change']:+,.0f}, {r['clicks_pct']:+.1f}%)")
        if r['pkg_impact']:
            lines.append(f"  主要影响包:")
            for p in r['pkg_impact'][:3]:
                if abs(p['rev_diff']) < 5:
                    continue
                pkg_dir = "↑" if p['rev_diff'] > 0 else "↓"
                lines.append(f"    {pkg_dir} {p['pkg'][:50]}: ${p['rev_prev']:,.2f}→${p['rev_now']:,.2f} ({p['rev_diff']:+,.2f})")

output = '\n'.join(lines)

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
print(output)

# 保存到文件
with open('advertiser_conclusion.txt', 'w', encoding='utf-8') as f:
    f.write(output)
