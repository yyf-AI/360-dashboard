"""Backfill 0927 data (T-2) with all publishers including 1000263."""

import json, time
from pathlib import Path
import requests as req

_DIR = Path(__file__).resolve().parent
DASHBOARD_DATA = _DIR / "360_dashboard_data.js"
KUBUUBI_CONFIG = Path(r"C:\Users\Mi\kyuubi-config.json")
BASE_URL = "http://proxy-service-http-alisgp0-dp.api.xiaomi.net"
PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260','1000262','1000263']

def load_token():
    with open(KUBUUBI_CONFIG) as f:
        cfg = json.load(f)
    tokens = cfg.get("tokens", [])
    t = tokens[0]
    return t["token"] if isinstance(t, dict) else t

def submit_sql(sql, token):
    headers = {"X-SqlProxy-User": token, "X-SqlProxy-Engine": "auto", "Content-Type": "text/plain;charset=utf-8"}
    resp = req.post(f"{BASE_URL}/olap/api/v2/statement/query", data=sql.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("meta", {}).get("errCode", -1) != 0:
        raise RuntimeError(f"Submit failed: {body}")
    return body["data"]["queryId"]

def poll_query(query_id, token, max_wait=300):
    headers = {"X-SqlProxy-User": token}
    elapsed = 0
    while elapsed < max_wait:
        resp = req.post(f"{BASE_URL}/olap/api/v2/statement/getStatusAndLog", params={"queryId": query_id}, headers=headers, timeout=30)
        body = resp.json()
        data = body.get("data", {})
        state = data.get("state", "")
        if data.get("nextQueryId"):
            query_id = data["nextQueryId"]
        if state == "FINISHED":
            return query_id
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Query {state}")
        time.sleep(3)
        elapsed += 3
    raise RuntimeError("Query timed out")

def fetch_results(query_id, token):
    headers = {"X-SqlProxy-User": token}
    all_rows = []
    columns = None
    qid = query_id
    while qid:
        resp = req.post(f"{BASE_URL}/olap/api/v2/statement/fetchResult", params={"queryId": qid}, headers=headers, timeout=60)
        body = resp.json()
        data = body.get("data", {})
        if columns is None and data.get("columns"):
            columns = data["columns"]
        all_rows.extend(data.get("rows", []))
        qid = data.get("nextResultQueryId")
    return columns, all_rows

date_str = "20260927"

sql = f"""
SELECT
    a.campaign_id, a.publisher_id,
    b.package_name, b.advertiser_name, b.advertiser_id,
    a.revenue, a.conversions, a.block, a.pa_cnt
FROM (
    SELECT campaign_id, publisher_id, SUM(revenue) AS revenue, SUM(conversions) AS conversions,
           SUM(block) AS block, SUM(pa_cnt) AS pa_cnt
    FROM iceberg_alsgprc_hadoop.miuiads.ads_offline_pb_pa_1d
    WHERE date = {date_str} AND dsp_level1 IN ('milengine')
    GROUP BY campaign_id, publisher_id
) a
LEFT JOIN (
    SELECT campaign_id, MAX(package_name) AS package_name,
           MAX(get_json_object(info, '$.advertiser_name')) AS advertiser_name,
           MAX(advertiser_id) AS advertiser_id
    FROM hive_alsgprc_hadoop.miuiads.postback_info_milengine
    WHERE date = {date_str}
    GROUP BY campaign_id
) b ON a.campaign_id = b.campaign_id
ORDER BY a.campaign_id, a.publisher_id
"""

token = load_token()
print(f"Submitting query for {date_str}...")
query_id = submit_sql(sql, token)
print(f"Query submitted: {query_id[:40]}...")
query_id = poll_query(query_id, token)
columns, rows = fetch_results(query_id, token)
print(f"Fetched {len(rows)} rows")

# Process
col_names = [c["name"] for c in columns]
campaigns = {}
for row in rows:
    r = dict(zip(col_names, row))
    cid = r["campaign_id"]
    if cid not in campaigns:
        campaigns[cid] = {
            "campaign_id": cid, "package_name": r.get("package_name") or "",
            "advertiser": "", "total_revenue": 0, "total_conversions": 0,
            "total_block": 0, "total_pa": 0, "pub_data": {}
        }
    c = campaigns[cid]
    c["total_revenue"] += r.get("revenue") or 0
    c["total_conversions"] += r.get("conversions") or 0
    c["total_block"] += r.get("block") or 0
    c["total_pa"] += r.get("pa_cnt") or 0
    if r.get("package_name"):
        c["package_name"] = r["package_name"]
    adv = r.get("advertiser_name") or ""
    adv_id = r.get("advertiser_id")
    if adv_id and adv:
        c["advertiser"] = f"{adv}({adv_id})"
    elif adv:
        c["advertiser"] = adv

    pub_id = r["publisher_id"]
    if pub_id in PUBS:
        conv = r.get("conversions") or 0
        block = r.get("block") or 0
        pa = r.get("pa_cnt") or 0
        rev = r.get("revenue") or 0
        denom = block + conv
        pub_fraud = (pa + block) / denom if denom > 0 else 0
        c["pub_data"][pub_id] = {"fraud": pub_fraud, "revenue": rev, "conv": conv, "block": block, "pa": pa}

# Build records
result = []
for cid, c in campaigns.items():
    total_denom = c["total_block"] + c["total_conversions"]
    overall_fraud = (c["total_pa"] + c["total_block"]) / total_denom if total_denom > 0 else 0
    overall_block = c["total_block"] / total_denom if total_denom > 0 else 0
    overall_pa = c["total_pa"] / total_denom if total_denom > 0 else 0

    pub_fraud = {}
    pub_rev = {}
    pub_conv = {}
    pub_block_cnt = {}
    pub_pa_cnt = {}
    for p in PUBS:
        if p in c["pub_data"]:
            pub_fraud[p] = c["pub_data"][p]["fraud"]
            pub_rev[p] = c["pub_data"][p]["revenue"]
            pub_conv[p] = int(c["pub_data"][p]["conv"])
            pub_block_cnt[p] = int(c["pub_data"][p]["block"])
            pub_pa_cnt[p] = int(c["pub_data"][p]["pa"])
        else:
            pub_fraud[p] = 0
            pub_rev[p] = 0
            pub_conv[p] = 0
            pub_block_cnt[p] = 0
            pub_pa_cnt[p] = 0

    result.append({
        "campaign_id": cid,
        "advertiser": c["advertiser"],
        "package_name": c["package_name"],
        "revenue": c["total_revenue"],
        "conversions": c["total_conversions"],
        "overall_fraud": overall_fraud,
        "overall_block": overall_block,
        "overall_pa": overall_pa,
        "pub_fraud": pub_fraud,
        "pub_rev": pub_rev,
        "pub_revenue": pub_rev,
        "pub_conv": pub_conv,
        "pub_block": pub_block_cnt,
        "pub_pa": pub_pa_cnt,
        "period": "0927",
        "days": 1
    })

print(f"Processed {len(result)} campaigns for 0927")

# Read existing data and append
content = DASHBOARD_DATA.read_text(encoding="utf-8")
json_start = content.index('[')
json_end = content.rindex(']')
data = json.loads(content[json_start:json_end+1])
data.extend(result)
main_js = "var DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
DASHBOARD_DATA.write_text(main_js, encoding="utf-8")
print(f"Appended {len(result)} records. Total: {len(data)} records")
