import pandas as pd
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
first = dates[0]   # 2026/8/3
latest = dates[-1]  # 2026/8/13

# 按广告主+包名+日期汇总
adv_pkg = df.groupby(['advertiser', 'package_name', 'date']).agg({
    'clicks': 'sum', 'revenue': 'sum', 'conversions': 'sum'
}).reset_index()

# 按广告主+日期汇总
adv_daily = df.groupby(['advertiser', 'date']).agg({
    'clicks': 'sum', 'revenue': 'sum', 'conversions': 'sum'
}).reset_index()

# 按广告主汇总全周期
adv_total = df.groupby('advertiser').agg({
    'clicks': 'sum', 'revenue': 'sum', 'conversions': 'sum'
}).reset_index()

results = []

for adv in adv_daily['advertiser'].unique():
    adv_data = adv_daily[adv_daily['advertiser'] == adv].sort_values('date')
    first_row = adv_data[adv_data['date'] == first]
    last_row = adv_data[adv_data['date'] == latest]
    total = adv_total[adv_total['advertiser'] == adv]

    if len(first_row) == 0 or len(last_row) == 0:
        continue

    rev_first = first_row['revenue'].values[0]
    rev_last = last_row['revenue'].values[0]
    clicks_first = first_row['clicks'].values[0]
    clicks_last = last_row['clicks'].values[0]
    rev_change = rev_last - rev_first
    clicks_change = clicks_last - clicks_first
    rev_pct = (rev_change / rev_first * 100) if rev_first > 0 else 0
    clicks_pct = (clicks_change / clicks_first * 100) if clicks_first > 0 else 0

    total_rev = total['revenue'].values[0]
    total_clicks = total['clicks'].values[0]
    avg_rev = adv_data['revenue'].mean()
    avg_clicks = adv_data['clicks'].mean()

    rev_values = adv_data['revenue'].tolist()
    n = len(rev_values)
    mid = n // 2
    rev_first_half = sum(rev_values[:mid]) / mid if mid > 0 else 0
    rev_second_half = sum(rev_values[mid:]) / (n - mid) if (n - mid) > 0 else 0
    rev_trend = "上升" if rev_second_half > rev_first_half * 1.05 else "下降" if rev_second_half < rev_first_half * 0.95 else "平稳"

    adv_pkgs = adv_pkg[adv_pkg['advertiser'] == adv]
    pkg_impact = []

    for pkg in adv_pkgs['package_name'].unique():
        pkg_data = adv_pkgs[adv_pkgs['package_name'] == pkg]
        pkg_first = pkg_data[pkg_data['date'] == first]
        pkg_last = pkg_data[pkg_data['date'] == latest]

        pkg_rev_first = pkg_first['revenue'].values[0] if len(pkg_first) > 0 else 0
        pkg_rev_last = pkg_last['revenue'].values[0] if len(pkg_last) > 0 else 0
        pkg_rev_diff = pkg_rev_last - pkg_rev_first
        pkg_clicks_first = pkg_first['clicks'].values[0] if len(pkg_first) > 0 else 0
        pkg_clicks_last = pkg_last['clicks'].values[0] if len(pkg_last) > 0 else 0
        pkg_clicks_diff = pkg_clicks_last - pkg_clicks_first

        if abs(pkg_rev_diff) > 5 or abs(pkg_clicks_diff) > 5000:
            pkg_impact.append({
                'pkg': pkg,
                'rev_diff': pkg_rev_diff,
                'clicks_diff': pkg_clicks_diff,
                'rev_first': pkg_rev_first,
                'rev_last': pkg_rev_last
            })

    pkg_impact.sort(key=lambda x: abs(x['rev_diff']), reverse=True)

    results.append({
        'advertiser': adv,
        'rev_first': rev_first,
        'rev_last': rev_last,
        'rev_change': rev_change,
        'rev_pct': rev_pct,
        'clicks_first': clicks_first,
        'clicks_last': clicks_last,
        'clicks_change': clicks_change,
        'clicks_pct': clicks_pct,
        'total_rev': total_rev,
        'avg_rev': avg_rev,
        'rev_trend': rev_trend,
        'pkg_impact': pkg_impact[:5]
    })

results.sort(key=lambda x: x['rev_change'])

# 输出文字版
down = [r for r in results if r['rev_change'] < -10]
up = [r for r in results if r['rev_change'] > 10]

print(f"📋 数据变化结论总结（{first} → {latest}，共{len(dates)}天）")
print("=" * 70)
print(f"共{len(results)}个广告主，下滑{len(down)}个，增长{len(up)}个")
print()

if down:
    print("📉 收入下滑广告主（首日→末日）")
    print("-" * 70)
    for r in down:
        print(f"▶ {r['advertiser']}")
        print(f"  收入: ${r['rev_first']:,.2f} → ${r['rev_last']:,.2f} ({r['rev_change']:+,.2f}, {r['rev_pct']:+.1f}%)")
        print(f"  点击: {r['clicks_first']:,.0f} → {r['clicks_last']:,.0f} ({r['clicks_change']:+,.0f}, {r['clicks_pct']:+.1f}%)")
        print(f"  全周期总收入: ${r['total_rev']:,.2f} | 日均: ${r['avg_rev']:,.2f} | 趋势: {r['rev_trend']}")
        if r['pkg_impact']:
            print(f"  主要影响包:")
            for p in r['pkg_impact'][:3]:
                if abs(p['rev_diff']) < 5:
                    continue
                print(f"    {p['pkg'][:50]}: ${p['rev_first']:,.2f}→${p['rev_last']:,.2f} ({p['rev_diff']:+,.2f})")
        print()

if up:
    print("📈 收入增长广告主（首日→末日）")
    print("-" * 70)
    for r in up:
        print(f"▶ {r['advertiser']}")
        print(f"  收入: ${r['rev_first']:,.2f} → ${r['rev_last']:,.2f} ({r['rev_change']:+,.2f}, {r['rev_pct']:+.1f}%)")
        print(f"  点击: {r['clicks_first']:,.0f} → {r['clicks_last']:,.0f} ({r['clicks_change']:+,.0f}, {r['clicks_pct']:+.1f}%)")
        print(f"  全周期总收入: ${r['total_rev']:,.2f} | 日均: ${r['avg_rev']:,.2f} | 趋势: {r['rev_trend']}")
        if r['pkg_impact']:
            print(f"  主要影响包:")
            for p in r['pkg_impact'][:3]:
                if abs(p['rev_diff']) < 5:
                    continue
                print(f"    {p['pkg'][:50]}: ${p['rev_first']:,.2f}→${p['rev_last']:,.2f} ({p['rev_diff']:+,.2f})")
        print()
