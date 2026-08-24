"""
手动补缺失的360数据（0820, 0821, 0822）
"""
import json
import re
import time
import sys
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
import requests

# ============ 配置 ============
_DIR = Path(__file__).resolve().parent
DASHBOARD_DATA = _DIR / "360_dashboard_data.js"
KUBUUBI_CONFIG = Path(r"C:\Users\Mi\kyuubi-config.json")
LOG_FILE = _DIR / "fix_missing_data.log"

BASE_URL = "http://proxy-service-http-alisgp0-dp.api.xiaomi.net"
PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260','1000262']

SQL_TEMPLATE = """
SELECT
    a.campaign_id, a.publisher_id,
    b.package_name, b.advertiser_name, b.advertiser_id,
    a.revenue, a.conversions, a.block, a.pa_cnt,
    CASE WHEN (a.block + a.conversions) > 0
         THEN (a.pa_cnt + a.block) / (a.block + a.conversions) ELSE 0 END AS fraud_rate
FROM (
    SELECT campaign_id, publisher_id, SUM(revenue) AS revenue, SUM(conversions) AS conversions,
           SUM(block) AS block, SUM(pa_cnt) AS pa_cnt
    FROM iceberg_alsgprc_hadoop.miuiads.ads_offline_pb_pa_1d
    WHERE date = '{date}' AND dsp_level1 IN ('milengine')
    GROUP BY campaign_id, publisher_id
) a
LEFT JOIN (
    SELECT campaign_id, MAX(package_name) AS package_name,
           MAX(get_json_object(info, '$.advertiser_name')) AS advertiser_name,
           MAX(advertiser_id) AS advertiser_id
    FROM hive_alsgprc_hadoop.miuiads.postback_info_milengine
    WHERE date = '{date}'
    GROUP BY campaign_id
) b ON a.campaign_id = b.campaign_id
ORDER BY a.campaign_id, a.publisher_id
"""

# ============ 日志 ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ============ Kyuubi API（与原脚本一致） ============
def load_token():
    with open(KUBUUBI_CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    tokens = cfg.get("tokens", [])
    if not tokens:
        raise RuntimeError("No tokens found in kyuubi-config.json")
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


def poll_query(query_id, token, max_wait=600):
    """轮询查询状态（使用正确的API端点）"""
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
        time.sleep(2)
        elapsed += 2
    raise RuntimeError(f"Query timed out after {max_wait}s")


def fetch_results(query_id, token):
    """获取查询结果（使用正确的API端点）"""
    headers = {"X-SqlProxy-User": token}
    all_rows = []
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
        all_rows.extend(data.get("rows", []))
        qid = data.get("nextResultQueryId")
    return all_rows


def query_date(date_str, token):
    """查询单日数据"""
    sql = SQL_TEMPLATE.format(date=date_str)
    log.info(f"Submitting SQL for date={date_str}...")
    query_id = submit_sql(sql, token)
    log.info(f"Query submitted, id={query_id}")

    query_id = poll_query(query_id, token)
    log.info("Query finished, fetching results...")

    rows = fetch_results(query_id, token)
    log.info(f"Fetched {len(rows)} rows")
    return rows


def aggregate_campaigns(rows, period):
    """按campaign_id聚合publisher维度的行"""
    campaigns = {}
    for row in rows:
        cid = row[0]
        if not cid or cid == "":
            continue
        pub_id = str(row[1])
        rev = float(row[5] or 0)
        conv = int(row[6] or 0)
        block = float(row[7] or 0)
        pa = float(row[8] or 0)
        fraud = float(row[9] or 0)
        pkg = row[2] or ""
        adv = row[3] or ""

        if cid not in campaigns:
            campaigns[cid] = {
                "campaign_id": cid,
                "advertiser": adv,
                "package_name": pkg,
                "revenue": 0, "conversions": 0,
                "total_block": 0, "total_pa": 0,
                "pub_fraud": {}, "pub_rev": {},
            }
        c = campaigns[cid]
        c["revenue"] += rev
        c["conversions"] += conv
        c["total_block"] += block
        c["total_pa"] += pa
        c["pub_fraud"][pub_id] = fraud
        c["pub_rev"][pub_id] = rev
        if adv and not c["advertiser"]:
            c["advertiser"] = adv
        if pkg and not c["package_name"]:
            c["package_name"] = pkg

    records = []
    for c in campaigns.values():
        total_conv = c["conversions"]
        total_block = c["total_block"]
        total_pa = c["total_pa"]
        denom = total_block + total_conv
        records.append({
            "campaign_id": c["campaign_id"],
            "advertiser": c["advertiser"],
            "package_name": c["package_name"],
            "revenue": round(c["revenue"], 2),
            "conversions": c["conversions"],
            "overall_fraud": round((total_pa + total_block) / max(denom, 1), 4),
            "overall_block": round(total_block / max(denom, 1), 4),
            "overall_pa": round(total_pa / max(denom, 1), 4),
            "pub_fraud": {k: round(v, 4) for k, v in c["pub_fraud"].items()},
            "pub_rev": {k: round(v, 2) for k, v in c["pub_rev"].items()},
            "period": period,
            "days": 1
        })
    return records


def append_to_data_file(new_records, period):
    """追加新数据到JS文件"""
    with open(DASHBOARD_DATA, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取JSON数组（var 或 const）
    match = re.search(r'(?:var|const) DATA = (\[.*?\]);', content, re.DOTALL)
    if not match:
        raise RuntimeError("Cannot find DATA array in JS file")

    data = json.loads(match.group(1))

    # 移除同period的旧数据（如果有的话）
    data = [r for r in data if r.get("period") != period]

    # 追加新数据
    data.extend(new_records)

    # 写回
    new_content = f"const DATA = {json.dumps(data, ensure_ascii=False)};"
    with open(DASHBOARD_DATA, 'w', encoding='utf-8') as f:
        f.write(new_content)

    log.info(f"Appended {len(new_records)} records, period={period}")
    return len(data)


def update_html_cache_version():
    """更新HTML的缓存版本号"""
    now = datetime.now().strftime("%Y%m%d%H%M")
    for html_file in [_DIR / "360_dashboard.html", _DIR / "index.html"]:
        if html_file.exists():
            content = html_file.read_text(encoding='utf-8')
            new_content = re.sub(r'v=\d{12}', f'v={now}', content)
            html_file.write_text(new_content, encoding='utf-8')
            log.info(f"Bumped cache version in {html_file.name} to v={now}")


def git_push():
    """推送到GitHub"""
    try:
        os.chdir(_DIR)
        os.system("git add -A")
        os.system('git commit -m "补数据: 0820, 0821, 0822"')
        result = os.system("git push")
        if result == 0:
            log.info("Pushed to GitHub successfully")
        else:
            log.warning(f"Git push failed with code {result}")
    except Exception as e:
        log.error(f"Git push error: {e}")


def main():
    token = load_token()

    # 需要补的日期：0820, 0821, 0822
    missing_dates = [
        ("20260820", "0820"),
        ("20260821", "0821"),
        ("20260822", "0822"),
    ]

    total_added = 0
    for date_str, period in missing_dates:
        log.info(f"=== Processing {date_str} (period={period}) ===")
        try:
            rows = query_date(date_str, token)
            records = aggregate_campaigns(rows, period)
            append_to_data_file(records, period)
            total_added += len(records)
            log.info(f"=== Done: {len(records)} records for {period} ===")
        except Exception as e:
            log.error(f"Failed for {date_str}: {e}")
            import traceback
            traceback.print_exc()

    if total_added > 0:
        update_html_cache_version()
        git_push()

    log.info(f"\n=== All done! Total added: {total_added} records ===")
    print(f"\n完成！共添加 {total_added} 条记录")


if __name__ == "__main__":
    main()
