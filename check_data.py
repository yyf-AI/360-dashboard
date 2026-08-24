import re

with open('360_dashboard_data.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取所有period
periods = re.findall(r'"period":\s*"(\d+)"', content)
unique_periods = sorted(set(periods))
print('现有数据日期:', unique_periods[-10:] if len(unique_periods) > 10 else unique_periods)
print('最新日期:', unique_periods[-1] if unique_periods else '无')
print('总记录数:', len(periods))
