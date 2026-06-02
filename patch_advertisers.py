"""Patch missing advertiser names in 360_dashboard_data.js by querying postback_info_milengine."""
import json, re, time, sys, logging, requests
from pathlib import Path

_DIR = Path(__file__).resolve().parent
DASHBOARD_DATA = _DIR / "360_dashboard_data.js"
KUBUUBI_CONFIG = Path(r"C:\Users\Mi\kyuubi-config.json")
BASE_URL = "http://proxy-service-http-alisgp0-dp.api.xiaomi.net"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

def load_token():
    with open(KUBUUBI_CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    tokens = cfg.get("tokens", [])
    t = tokens[0]
    return t["token"] if isinstance(t, dict) else t

def submit_sql(sql, token):
    headers = {"X-SqlProxy-User": token, "X-SqlProxy-Engine": "auto", "Content-Type": "text/plain;charset=utf-8"}
    resp = requests.post(f"{BASE_URL}/olap/api/v2/statement/query", data=sql.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("meta", {}).get("errCode", -1) != 0:
        raise RuntimeError(f"Submit failed: {body}")
    return body["data"]["queryId"]

def poll_query(query_id, token, max_wait=600):
    headers = {"X-SqlProxy-User": token}
    elapsed = 0
    while elapsed < max_wait:
        resp = requests.post(f"{BASE_URL}/olap/api/v2/statement/getStatusAndLog", params={"queryId": query_id}, headers=headers, timeout=30)
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
        time.sleep(2)
        elapsed += 2
    raise RuntimeError(f"Query timed out after {max_wait}s")

def fetch_results(query_id, token):
    headers = {"X-SqlProxy-User": token}
    all_rows = []
    columns = None
    qid = query_id
    while qid:
        resp = requests.post(f"{BASE_URL}/olap/api/v2/statement/fetchResult", params={"queryId": qid}, headers=headers, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", {})
        if columns is None and data.get("columns"):
            columns = data["columns"]
        all_rows.extend(data.get("rows", []))
        qid = data.get("nextResultQueryId")
    return columns, all_rows

def query_advertiser_batch(campaign_ids, token):
    """Query postback_info_milengine for advertiser info for a batch of campaign_ids."""
    ids_str = ",".join(f"'{cid}'" for cid in campaign_ids)
    sql = f"""
SELECT campaign_id,
       MAX(get_json_object(info, '$.advertiser_name')) AS advertiser_name,
       MAX(advertiser_id) AS advertiser_id
FROM hive_alsgprc_hadoop.miuiads.postback_info_milengine
WHERE campaign_id IN ({ids_str})
GROUP BY campaign_id
"""
    log.info(f"Querying advertiser info for {len(campaign_ids)} campaign_ids...")
    query_id = submit_sql(sql, token)
    query_id = poll_query(query_id, token)
    columns, rows = fetch_results(query_id, token)
    log.info(f"Got {len(rows)} results")
    return {str(row[0]): (row[1], row[2]) for row in rows if row[1]}

def main():
    content = DASHBOARD_DATA.read_text(encoding="utf-8")
    match = re.search(r'const\s+DATA\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if not match:
        log.error("Cannot parse DATA from JS file")
        return
    data = json.loads(match.group(1))

    # Find all campaign_ids missing advertiser
    missing_cids = set()
    for d in data:
        if not d.get('advertiser') or not d['advertiser'].strip():
            missing_cids.add(d['campaign_id'])

    log.info(f"Total campaign_ids missing advertiser: {len(missing_cids)}")

    if not missing_cids:
        log.info("Nothing to patch")
        return

    token = load_token()

    # Query in batches of 100
    cid_list = list(missing_cids)
    advertiser_map = {}
    for i in range(0, len(cid_list), 100):
        batch = cid_list[i:i+100]
        log.info(f"Batch {i//100+1}: querying {len(batch)} ids...")
        try:
            result = query_advertiser_batch(batch, token)
            advertiser_map.update(result)
            log.info(f"Got {len(result)} advertiser mappings")
        except Exception as e:
            log.error(f"Batch failed: {e}")

    log.info(f"Total advertiser mappings found: {len(advertiser_map)}")

    # Patch the data
    patched = 0
    for d in data:
        if not d.get('advertiser') or not d['advertiser'].strip():
            cid = d['campaign_id']
            if cid in advertiser_map:
                adv_name, adv_id = advertiser_map[cid]
                if adv_id:
                    d['advertiser'] = f"{adv_name}({adv_id})" if adv_name else ""
                else:
                    d['advertiser'] = adv_name or ""
                patched += 1

    log.info(f"Patched {patched} records")

    # Write back
    new_js = "const DATA = " + json.dumps(data, ensure_ascii=False) + ";"
    DASHBOARD_DATA.write_text(new_js, encoding="utf-8")
    log.info("Data file updated")

    # Verify
    remaining = sum(1 for d in data if not d.get('advertiser') or not d['advertiser'].strip())
    log.info(f"Remaining records without advertiser: {remaining}")

if __name__ == "__main__":
    main()
