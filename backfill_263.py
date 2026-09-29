"""
Backfill publisher 1000263 data into existing 360 dashboard data file.
Queries the database for each period and adds pub_ fields for 1000263.
"""

import json
import time
from pathlib import Path
import requests

_DIR = Path(__file__).resolve().parent
DASHBOARD_DATA = _DIR / "360_dashboard_data.js"
KUBUUBI_CONFIG = Path(r"C:\Users\Mi\kyuubi-config.json")
BASE_URL = "http://proxy-service-http-alisgp0-dp.api.xiaomi.net"
PUB_TO_ADD = '1000263'

SQL_TEMPLATE = """
SELECT
    a.campaign_id, a.publisher_id,
    a.revenue, a.conversions, a.block, a.pa_cnt
FROM (
    SELECT campaign_id, publisher_id, SUM(revenue) AS revenue, SUM(conversions) AS conversions,
           SUM(block) AS block, SUM(pa_cnt) AS pa_cnt
    FROM iceberg_alsgprc_hadoop.miuiads.ads_offline_pb_pa_1d
    WHERE date = {date} AND dsp_level1 IN ('milengine')
    AND publisher_id = '{pub_id}'
    GROUP BY campaign_id, publisher_id
) a
ORDER BY a.campaign_id
"""


def load_token():
    with open(KUBUUBI_CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    tokens = cfg.get("tokens", [])
    if not tokens:
        raise RuntimeError("No tokens found")
    t = tokens[0]
    return t["token"] if isinstance(t, dict) else t


def submit_sql(sql, token):
    headers = {
        "X-SqlProxy-User": token,
        "X-SqlProxy-Engine": "auto",
        "Content-Type": "text/plain;charset=utf-8",
    }
    resp = requests.post(f"{BASE_URL}/olap/api/v2/statement/query", data=sql.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("meta", {}).get("errCode", -1) != 0:
        raise RuntimeError(f"Submit failed: {body}")
    return body["data"]["queryId"]


def poll_query(query_id, token, max_wait=300):
    headers = {"X-SqlProxy-User": token}
    elapsed = 0
    while elapsed < max_wait:
        resp = requests.post(
            f"{BASE_URL}/olap/api/v2/statement/getStatusAndLog",
            params={"queryId": query_id},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", {})
        state = data.get("state", "")
        if data.get("nextQueryId"):
            query_id = data["nextQueryId"]
        if state == "FINISHED":
            return query_id
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Query {state}: {data.get('exceptionMsg', '')}")
        time.sleep(3)
        elapsed += 3
    raise RuntimeError(f"Query timed out after {max_wait}s")


def fetch_results(query_id, token):
    headers = {"X-SqlProxy-User": token}
    all_rows = []
    columns = None
    qid = query_id
    while qid:
        resp = requests.post(
            f"{BASE_URL}/olap/api/v2/statement/fetchResult",
            params={"queryId": qid},
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", {})
        if columns is None and data.get("columns"):
            columns = data["columns"]
        all_rows.extend(data.get("rows", []))
        qid = data.get("nextResultQueryId")
    return columns, all_rows


def query_263_data(date_int, token):
    sql = SQL_TEMPLATE.format(date=date_int, pub_id=PUB_TO_ADD)
    query_id = submit_sql(sql, token)
    print(f"  Query submitted: {query_id[:30]}...")
    query_id = poll_query(query_id, token)
    columns, rows = fetch_results(query_id, token)
    return columns, rows


def date_from_period(period):
    month = int(period[:2])
    day = int(period[2:])
    return 2026 * 10000 + month * 100 + day


def main():
    content = DASHBOARD_DATA.read_text(encoding="utf-8")
    data = json.loads(content[content.index('['):])

    periods = sorted(set(d['period'] for d in data if d.get('period') and len(d['period']) == 4))
    print(f"Found {len(periods)} periods in data file")

    # Check which periods already have 263 data with non-zero values
    has_263 = set()
    missing = set()
    for d in data:
        p = d['period']
        val = d.get('pub_fraud', {}).get(PUB_TO_ADD)
        if val is not None and val != 0:
            has_263.add(p)
        else:
            missing.add(p)

    print(f"Periods with 263 data: {sorted(has_263) if has_263 else 'none'}")
    print(f"Periods missing 263 data: {sorted(missing)}")

    if not missing:
        print("All periods already have 263 data!")
        return

    token = load_token()
    print(f"\nQuerying database for {len(missing)} periods...")

    for period in sorted(missing):
        date_int = date_from_period(period)
        print(f"\n--- Period {period} (date={date_int}) ---")

        try:
            columns, rows = query_263_data(date_int, token)
        except Exception as e:
            print(f"  ERROR querying {period}: {e}")
            continue

        if not rows:
            print(f"  No data for period {period}")
            continue

        # Build lookup: campaign_id -> pub data
        col_names = [c["name"] for c in columns] if columns else []
        pub_lookup = {}
        for row in rows:
            r = dict(zip(col_names, row)) if col_names else {}
            cid = r.get("campaign_id", row[0] if row else "")
            conv = r.get("conversions", row[4] if len(row) > 4 else 0) or 0
            block = r.get("block", row[5] if len(row) > 5 else 0) or 0
            pa = r.get("pa_cnt", row[6] if len(row) > 6 else 0) or 0
            rev = r.get("revenue", row[3] if len(row) > 3 else 0) or 0
            denom = block + conv
            pub_fraud = (pa + block) / denom if denom > 0 else 0
            pub_lookup[cid] = {
                "fraud": pub_fraud,
                "revenue": rev,
                "conv": int(conv),
                "block": int(block),
                "pa": int(pa)
            }

        print(f"  Found {len(pub_lookup)} campaigns with 263 data")

        # Update existing records for this period
        updated = 0
        for d in data:
            if d['period'] == period:
                cid = d['campaign_id']
                # Initialize 263 fields if not present
                d.setdefault('pub_fraud', {})[PUB_TO_ADD] = d.get('pub_fraud', {}).get(PUB_TO_ADD, 0)
                d.setdefault('pub_rev', {})[PUB_TO_ADD] = d.get('pub_rev', {}).get(PUB_TO_ADD, 0)
                d.setdefault('pub_revenue', {})[PUB_TO_ADD] = d.get('pub_revenue', {}).get(PUB_TO_ADD, 0)
                d.setdefault('pub_conv', {})[PUB_TO_ADD] = d.get('pub_conv', {}).get(PUB_TO_ADD, 0)
                d.setdefault('pub_block', {})[PUB_TO_ADD] = d.get('pub_block', {}).get(PUB_TO_ADD, 0)
                d.setdefault('pub_pa', {})[PUB_TO_ADD] = d.get('pub_pa', {}).get(PUB_TO_ADD, 0)

                if cid in pub_lookup:
                    p = pub_lookup[cid]
                    d['pub_fraud'][PUB_TO_ADD] = p['fraud']
                    d['pub_rev'][PUB_TO_ADD] = p['revenue']
                    d['pub_revenue'][PUB_TO_ADD] = p['revenue']
                    d['pub_conv'][PUB_TO_ADD] = p['conv']
                    d['pub_block'][PUB_TO_ADD] = p['block']
                    d['pub_pa'][PUB_TO_ADD] = p['pa']
                    updated += 1

        print(f"  Updated {updated} records for period {period}")

    # Write back
    main_js = 'var DATA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'
    DASHBOARD_DATA.write_text(main_js, encoding="utf-8")
    print(f"\nDone! Wrote {len(data)} records to {DASHBOARD_DATA.name}")


if __name__ == "__main__":
    main()
