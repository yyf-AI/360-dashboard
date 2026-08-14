import pandas as pd
import json

# 读取数据
df = pd.read_csv(r'C:\Users\Mi\Downloads\report_export - 2026-08-14T170947.636.csv')

# 清洗数据
for col in ['clicks', 'revenue', 'payout', 'profit', 'conversions', 'postback_conversions']:
    df[col] = df[col].astype(str).str.replace(',', '').astype(float)

df = df.rename(columns={
    'groupby_1': 'date',
    'groupby_2': 'package_name',
    'groupby_3': 'advertiser',
    'groupby_4': 'extra'
})

# 按advertiser和date汇总
adv_daily = df.groupby(['advertiser', 'date']).agg({
    'clicks': 'sum',
    'revenue': 'sum',
    'conversions': 'sum'
}).reset_index()

# 排序日期
def date_sort_key(d):
    parts = d.split('/')
    return int(parts[0]) * 10000 + int(parts[1]) * 100 + int(parts[2])

dates = sorted(adv_daily['date'].unique(), key=date_sort_key)

# 计算各advertiser的总量
adv_total = df.groupby('advertiser').agg({
    'clicks': 'sum',
    'revenue': 'sum',
    'conversions': 'sum'
}).reset_index()

# 计算环比
latest = dates[-1]
prev = dates[-2]

result = []
for adv in adv_total['advertiser']:
    latest_data = adv_daily[(adv_daily['advertiser'] == adv) & (adv_daily['date'] == latest)]
    prev_data = adv_daily[(adv_daily['advertiser'] == adv) & (adv_daily['date'] == prev)]
    total_data = adv_total[adv_total['advertiser'] == adv]

    if len(latest_data) > 0 and len(prev_data) > 0:
        clicks_now = latest_data['clicks'].values[0]
        clicks_prev = prev_data['clicks'].values[0]
        rev_now = latest_data['revenue'].values[0]
        rev_prev = prev_data['revenue'].values[0]
        total_rev = total_data['revenue'].values[0]
        total_clicks = total_data['clicks'].values[0]

        clicks_change = clicks_now - clicks_prev
        rev_change = rev_now - rev_prev
        clicks_pct = (clicks_change / clicks_prev * 100) if clicks_prev > 0 else 0
        rev_pct = (rev_change / rev_prev * 100) if rev_prev > 0 else 0

        result.append({
            'advertiser': adv,
            'total_rev': total_rev,
            'total_clicks': total_clicks,
            'clicks_latest': clicks_now,
            'clicks_prev': clicks_prev,
            'clicks_change': clicks_change,
            'clicks_pct': clicks_pct,
            'revenue_latest': rev_now,
            'revenue_prev': rev_prev,
            'revenue_change': rev_change,
            'revenue_pct': rev_pct
        })

result_df = pd.DataFrame(result)
result_df = result_df.sort_values('revenue_change')

# 生成趋势数据
trend_data = {}
for adv in adv_daily['advertiser'].unique():
    adv_df = adv_daily[adv_daily['advertiser'] == adv]
    trend_data[adv] = {
        'clicks': [adv_df[adv_df['date'] == d]['clicks'].values[0] if len(adv_df[adv_df['date'] == d]) > 0 else 0 for d in dates],
        'revenue': [adv_df[adv_df['date'] == d]['revenue'].values[0] if len(adv_df[adv_df['date'] == d]) > 0 else 0 for d in dates]
    }

# 构建表格行
def build_rows(df_slice, label):
    rows_html = ''
    for _, row in df_slice.iterrows():
        chg_cls = 'negative' if row['revenue_change'] < 0 else 'positive' if row['revenue_change'] > 0 else 'neutral'
        rows_html += f'''<tr>
            <td>{row["advertiser"]}</td>
            <td class="num">{row["total_clicks"]:,.0f}</td>
            <td class="num">${row["total_rev"]:,.2f}</td>
            <td class="num">{row["clicks_latest"]:,.0f}</td>
            <td class="num">{row["clicks_prev"]:,.0f}</td>
            <td class="num {chg_cls}">{row["clicks_change"]:+,.0f}</td>
            <td class="num {chg_cls}">{row["clicks_pct"]:+.1f}%</td>
            <td class="num">${row["revenue_latest"]:,.2f}</td>
            <td class="num">${row["revenue_prev"]:,.2f}</td>
            <td class="num {chg_cls}">{row["revenue_change"]:+,.2f}</td>
            <td class="num {chg_cls}">{row["revenue_pct"]:+.1f}%</td>
        </tr>'''
    return rows_html

# 广告主标签JS
adv_list = result_df.head(5)['advertiser'].tolist() + result_df.tail(5)['advertiser'].tolist()
adv_list.reverse()  # 增长的在前
adv_js = json.dumps(adv_list, ensure_ascii=False)

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advertiser维度 点击&收入趋势分析</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{ text-align: center; margin-bottom: 6px; color: #1a237e; }}
        .subtitle {{ text-align: center; color: #666; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); padding: 24px; margin-bottom: 24px; overflow-x: auto; }}
        .card h2 {{ font-size: 18px; color: #333; margin-bottom: 16px; border-left: 4px solid #1976d2; padding-left: 12px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; white-space: nowrap; }}
        th {{ background: #f0f4f8; color: #555; padding: 10px 12px; text-align: left; border-bottom: 2px solid #e0e6ed; position: sticky; top: 0; }}
        td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f5f7fa; }}
        .num {{ text-align: right; font-family: 'SF Mono', Consolas, monospace; }}
        .positive {{ color: #e53935; font-weight: 600; }}
        .negative {{ color: #43a047; font-weight: 600; }}
        .neutral {{ color: #999; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
        .summary-item {{ background: white; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }}
        .summary-item .label {{ color: #666; font-size: 14px; margin-bottom: 8px; }}
        .summary-item .value {{ font-size: 28px; font-weight: bold; color: #1a237e; }}
        .chart-container {{ position: relative; height: 420px; }}
        .tabs {{ display: flex; gap: 6px; margin-bottom: 16px; flex-wrap: wrap; }}
        .tab {{ padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 12px; border: 1px solid #ddd; background: white; transition: all 0.2s; }}
        .tab:hover {{ border-color: #1976d2; }}
        .tab.active {{ background: #1976d2; color: white; border-color: #1976d2; }}
        @media (max-width: 768px) {{
            .summary {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Advertiser维度 点击&收入趋势分析</h1>
        <p class="subtitle">数据周期: {dates[0]} ~ {dates[-1]} | {len(dates)}天 | {len(adv_total)}个Advertiser</p>

        <div class="summary">
            <div class="summary-item">
                <div class="label">总点击</div>
                <div class="value">{result_df["total_clicks"].sum():,.0f}</div>
            </div>
            <div class="summary-item">
                <div class="label">总收入</div>
                <div class="value">${result_df["total_rev"].sum():,.2f}</div>
            </div>
            <div class="summary-item">
                <div class="label">最新日({latest})点击</div>
                <div class="value">{result_df["clicks_latest"].sum():,.0f}</div>
            </div>
            <div class="summary-item">
                <div class="label">最新日({latest})收入</div>
                <div class="value">${result_df["revenue_latest"].sum():,.2f}</div>
            </div>
        </div>

        <div class="card">
            <h2>收入下滑TOP10（{prev} vs {latest}）</h2>
            <table>
                <thead>
                    <tr>
                        <th>Advertiser</th>
                        <th class="num">总点击</th>
                        <th class="num">总收入</th>
                        <th class="num">最新日点击</th>
                        <th class="num">前日点击</th>
                        <th class="num">点击变化</th>
                        <th class="num">点击%</th>
                        <th class="num">最新日收入</th>
                        <th class="num">前日收入</th>
                        <th class="num">收入变化</th>
                        <th class="num">收入%</th>
                    </tr>
                </thead>
                <tbody>
                    {build_rows(result_df.head(10), 'down')}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>收入增长TOP10（{prev} vs {latest}）</h2>
            <table>
                <thead>
                    <tr>
                        <th>Advertiser</th>
                        <th class="num">总点击</th>
                        <th class="num">总收入</th>
                        <th class="num">最新日点击</th>
                        <th class="num">前日点击</th>
                        <th class="num">点击变化</th>
                        <th class="num">点击%</th>
                        <th class="num">最新日收入</th>
                        <th class="num">前日收入</th>
                        <th class="num">收入变化</th>
                        <th class="num">收入%</th>
                    </tr>
                </thead>
                <tbody>
                    {build_rows(result_df.tail(10).iloc[::-1], 'up')}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>点击&收入趋势图（切换Advertiser查看）</h2>
            <div class="tabs" id="adv-tabs"></div>
            <div class="chart-container">
                <canvas id="trendChart"></canvas>
            </div>
        </div>

        <div class="card">
            <h2>全量Advertiser数据</h2>
            <table>
                <thead>
                    <tr>
                        <th>Advertiser</th>
                        <th class="num">总点击</th>
                        <th class="num">总收入</th>
                        <th class="num">最新日点击</th>
                        <th class="num">前日点击</th>
                        <th class="num">点击变化</th>
                        <th class="num">点击%</th>
                        <th class="num">最新日收入</th>
                        <th class="num">前日收入</th>
                        <th class="num">收入变化</th>
                        <th class="num">收入%</th>
                    </tr>
                </thead>
                <tbody>
                    {build_rows(result_df.iloc[::-1], 'all')}
                </tbody>
            </table>
        </div>
    </div>

    <script>
    const trendData = {json.dumps({"dates": dates, "data": trend_data}, ensure_ascii=False)};

    const advList = {adv_js};
    const tabsContainer = document.getElementById('adv-tabs');

    advList.forEach((adv, i) => {{
        const tab = document.createElement('div');
        tab.className = 'tab' + (i === 0 ? ' active' : '');
        tab.textContent = adv.split('(')[0].substring(0, 20);
        tab.title = adv;
        tab.onclick = function() {{ showAdv(adv, this); }};
        tabsContainer.appendChild(tab);
    }});

    const ctx = document.getElementById('trendChart').getContext('2d');
    let chart = null;

    function showAdv(adv, el) {{
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        if (el) el.classList.add('active');

        const data = trendData.data[adv];
        if (!data) return;

        if (chart) chart.destroy();

        chart = new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: trendData.dates,
                datasets: [
                    {{
                        label: '点击',
                        data: data.clicks,
                        borderColor: '#42a5f5',
                        backgroundColor: 'rgba(66,165,245,0.1)',
                        yAxisID: 'y',
                        tension: 0.3,
                        fill: true
                    }},
                    {{
                        label: '收入($)',
                        data: data.revenue,
                        borderColor: '#66bb6a',
                        backgroundColor: 'rgba(102,187,106,0.1)',
                        yAxisID: 'y1',
                        tension: 0.3,
                        fill: true
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{ mode: 'index', intersect: false }},
                plugins: {{
                    title: {{ display: true, text: adv, font: {{ size: 16 }} }}
                }},
                scales: {{
                    y: {{
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {{ display: true, text: '点击' }}
                    }},
                    y1: {{
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {{ display: true, text: '收入($)' }},
                        grid: {{ drawOnChartArea: false }}
                    }}
                }}
            }}
        }});
    }}

    if (advList.length > 0) showAdv(advList[0], document.querySelector('.tab'));
    </script>
</body>
</html>'''

with open(r'C:\Users\Mi\360_dashboard\advertiser_trend_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'看板已生成: advertiser_trend_dashboard.html')
print(f'日期范围: {dates[0]} ~ {dates[-1]}')
print(f'Advertiser数量: {len(adv_total)}')
print(f'\n=== 收入下滑TOP5 ===')
for _, r in result_df.head(5).iterrows():
    print(f"  {r['advertiser']}: ${r['revenue_change']:+,.2f} ({r['revenue_pct']:+.1f}%)")
print(f'\n=== 收入增长TOP5 ===')
for _, r in result_df.tail(5).iloc[::-1].iterrows():
    print(f"  {r['advertiser']}: ${r['revenue_change']:+,.2f} ({r['revenue_pct']:+.1f}%)")
