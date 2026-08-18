#!/usr/bin/env python3
"""
补数据脚本：获取0813、0814的数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from update_360_dashboard import query_360_data, process_data, append_data, load_token

token = load_token()

# 要补的日期
dates_to_backfill = ['20260813', '20260814']

for date in dates_to_backfill:
    period = date[4:]  # MMDD
    print(f"\n{'='*50}")
    print(f"Processing {date} (period: {period})")
    print('='*50)

    # 查询数据
    raw_data = query_360_data(date, token)
    if not raw_data:
        print(f"No data for {date}")
        continue

    # 处理数据
    processed = process_data(raw_data)
    print(f"Processed {len(processed)} records")

    # 写入数据
    append_data(processed, period)
    print(f"Successfully appended data for {period}")

print("\nDone! All missing dates have been backfilled.")
