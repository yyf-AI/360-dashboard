import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

JS_PATH = r"C:\Users\Mi\360_dashboard\360_dashboard_data.js"

# Load current data (0721-0725 with pub_conv/pub_block/pub_pa)
with open(JS_PATH, 'r', encoding='utf-8') as f:
    content = f.read()
import re
match = re.search(r'const DATA = (\[.*?\]);', content, re.DOTALL)
current_data = json.loads(match.group(1))
print(f"Current data: {len(current_data)} entries, periods: {sorted(set(d['period'] for d in current_data))}")

# Check if0726 and0727 exist
has_0726 = any(d['period'] == '0726' for d in current_data)
has_0727 = any(d['period'] == '0727' for d in current_data)
print(f"Has 0726: {has_0726}, Has 0727: {has_0727}")

if not has_0726 or not has_0727:
    # Need to query0726 and0727
    print("Need to query 0726 and 0727 data")
    # For now, let's check what we have
    print("Current periods:", sorted(set(d['period'] for d in current_data)))
