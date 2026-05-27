"""
360看板自动更新脚本
每天查询T-2日期的360数据，追加到看板数据文件并更新HTML按钮。
"""

import json
import re
import time
import sys
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import requests

# ============ 配置 ============
_DIR = Path(__file__).resolve().parent
DASHBOARD_HTML = _DIR / "360_dashboard.html"
DASHBOARD_DATA = _DIR / "360_dashboard_data.js"
KUBUUBI_CONFIG = Path(r"C:\Users\Mi\kyuubi-config.json")
LOG_FILE = _DIR / "update_360_dashboard.log"

BASE_URL = "http://proxy-service-http-alisgp0-dp.api.xiaomi.net"
PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260']
PUB_SHORT = ['218','220','222','223','224','226','253','254','255','260']
WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/8843f281-2440-4f13-a75f-4ef0e7a815d4"

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
    WHERE date = '{date}'
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

# ============ Kyuubi API ============
def load_token():
    with open(KUBUUBI_CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    tokens = cfg.get("tokens", [])
    if not tokens:
        raise RuntimeError("No tokens found in kyuubi-config.json")
    # tokens can be strings or dicts
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


def query_360_data(date_str, token):
    sql = SQL_TEMPLATE.format(date=date_str)
    log.info(f"Submitting SQL for date={date_str}...")
    query_id = submit_sql(sql, token)
    log.info(f"Query submitted, id={query_id}")
    query_id = poll_query(query_id, token)
    log.info("Query finished, fetching results...")
    columns, rows = fetch_results(query_id, token)
    log.info(f"Fetched {len(rows)} rows")
    return rows


# ============ 数据处理 ============
def process_data(rows):
    campaigns = {}
    for row in rows:
        cid = row[0]
        if not cid or cid == "":
            continue  # skip summary row
        if cid not in campaigns:
            campaigns[cid] = {
                "campaign_id": cid,
                "package_name": row[2],
                "advertiser_name": row[3],
                "advertiser_id": row[4],
                "total_revenue": 0,
                "total_conversions": 0,
                "total_block": 0,
                "total_pa": 0,
                "pub_data": {},
            }
        c = campaigns[cid]
        c["total_revenue"] += row[5] or 0
        c["total_conversions"] += row[6] or 0
        c["total_block"] += row[7] or 0
        c["total_pa"] += row[8] or 0

        pub_id = row[1]
        if pub_id in PUBS:
            pub_conv = row[6] or 0
            pub_block = row[7] or 0
            pub_pa = row[8] or 0
            pub_rev = row[5] or 0
            denom = pub_block + pub_conv
            pub_fraud = (pub_pa + pub_block) / denom if denom > 0 else 0
            c["pub_data"][pub_id] = {"fraud": pub_fraud, "revenue": pub_rev}

    result = []
    for cid, c in campaigns.items():
        total_denom = c["total_block"] + c["total_conversions"]
        overall_fraud = (c["total_pa"] + c["total_block"]) / total_denom if total_denom > 0 else 0
        overall_block = c["total_block"] / total_denom if total_denom > 0 else 0
        overall_pa = c["total_pa"] / total_denom if total_denom > 0 else 0

        adv = c["advertiser_name"] or ""
        adv_id = c["advertiser_id"]
        advertiser = f"{adv}({adv_id})" if adv_id and adv else adv

        pub_fraud = {}
        pub_rev = {}
        for p in PUBS:
            if p in c["pub_data"]:
                pub_fraud[p] = c["pub_data"][p]["fraud"]
                pub_rev[p] = c["pub_data"][p]["revenue"]
            else:
                pub_fraud[p] = 0
                pub_rev[p] = 0

        result.append({
            "campaign_id": cid,
            "advertiser": advertiser,
            "package_name": c["package_name"] or "",
            "revenue": round(c["total_revenue"], 2),
            "conversions": int(c["total_conversions"]),
            "overall_fraud": round(overall_fraud, 6),
            "overall_block": round(overall_block, 6),
            "overall_pa": round(overall_pa, 6),
            "pub_fraud": pub_fraud,
            "pub_revenue": pub_rev,
            "pub_rev": pub_rev,
            "period": "",  # filled later
            "days": 1,
        })

    result.sort(key=lambda x: x["revenue"], reverse=True)
    return result


# ============ 文件操作 ============
def get_existing_periods():
    content = DASHBOARD_DATA.read_text(encoding="utf-8")
    return set(re.findall(r'"period":\s*"([^"]+)"', content))


def append_data(records, period):
    for r in records:
        r["period"] = period

    content = DASHBOARD_DATA.read_text(encoding="utf-8")
    last_bracket = content.rfind("]")
    if last_bracket == -1:
        raise RuntimeError("Cannot find closing bracket in data file")

    new_entries = [json.dumps(item, ensure_ascii=False) for item in records]
    new_js = ",\n" + ",\n".join(new_entries)
    updated = content[:last_bracket] + new_js + content[last_bracket:]
    DASHBOARD_DATA.write_text(updated, encoding="utf-8")
    log.info(f"Appended {len(records)} records, period={period}")


# ============ 工具函数 ============
def extract_team(advertiser):
    """从advertiser字段提取团队名，如 '中国出海(1000358)' → '中国出海'"""
    if not advertiser:
        return '其他代理'
    m = re.match(r'^(.+?)\(', advertiser)
    return m.group(1) if m else advertiser


def format_report_content(rows, total_rev, label):
    """按团队→包→渠道格式化飞书消息内容"""
    from collections import defaultdict

    # Group by team → package
    by_team = defaultdict(lambda: {'count': 0, 'total_rev': 0, 'packages': defaultdict(lambda: {'total_rev': 0, 'items': []})})
    for r in rows:
        team = extract_team(r.get('advertiser', ''))
        pkg = r['package_name']
        by_team[team]['count'] += 1
        by_team[team]['total_rev'] += r['revenue']
        by_team[team]['packages'][pkg]['total_rev'] += r['revenue']
        by_team[team]['packages'][pkg]['items'].append(r)

    content_lines = [
        [{"tag": "text", "text": f"筛选：{label} | 共{len(rows)}条 | 总收入${total_rev:,.0f}/天\n"}],
        [{"tag": "text", "text": "━━━━━━━━━━━━━━━━━━━━━━\n"}],
    ]
    for team, info in sorted(by_team.items(), key=lambda x: -x[1]['total_rev']):
        content_lines.append([{"tag": "text", "text": f"【{team}】{info['count']}条 · ${info['total_rev']:,.0f}/天\n"}])
        for pkg, pkg_info in sorted(info['packages'].items(), key=lambda x: -x[1]['total_rev']):
            content_lines.append([{"tag": "text", "text": f"{pkg}\n"}])
            for item in sorted(pkg_info['items'], key=lambda x: -x['revenue'], reverse=True):
                content_lines.append([{"tag": "text", "text": f"  {item['publisher']} → ${item['revenue']:,.0f} | {item['fraud']*100:.1f}%\n"}])
        content_lines.append([{"tag": "text", "text": "\n"}])

    return content_lines


# ============ 高收入高作弊渠道推送 ============
def send_high_fraud_report(period):
    """推送指定日期的高收入高作弊渠道明细到飞书群"""
    from collections import defaultdict

    content = DASHBOARD_DATA.read_text(encoding="utf-8")
    match = re.search(r'const\s+DATA\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if not match:
        log.warning("Cannot parse DATA from JS file, skipping report")
        return
    data = json.loads(match.group(1))

    raw = [d for d in data if d['period'] == period]
    if not raw:
        log.warning(f"No data found for period {period}, skipping report")
        return
    pub_map = dict(zip(PUBS, PUB_SHORT))

    # Aggregate by campaign_id × publisher
    pub_detail = defaultdict(lambda: defaultdict(lambda: {
        'package_name': '', 'campaign_id': '', 'advertiser': '',
        'totalRev': 0, 'fraudNum': 0, 'convSum': 0
    }))
    for d in raw:
        cid = d['campaign_id']
        for p in PUBS:
            rev = (d.get('pub_rev') or {}).get(p, 0)
            if rev <= 0:
                continue
            g = pub_detail[p][cid]
            g['package_name'] = d['package_name']
            g['campaign_id'] = cid
            g['advertiser'] = d.get('advertiser', '')
            g['totalRev'] += rev
            f = (d.get('pub_fraud') or {}).get(p, 0)
            g['fraudNum'] += f * d['conversions']
            g['convSum'] += d['conversions']

    # Filter: rev >= $100, fraud > 20%
    rows = []
    for p in PUBS:
        for cid, g in pub_detail[p].items():
            fraud = g['fraudNum'] / g['convSum'] if g['convSum'] > 0 else 0
            if g['totalRev'] < 100 or fraud <= 0.2:
                continue
            rows.append({'publisher': pub_map[p], 'package_name': g['package_name'],
                         'advertiser': g['advertiser'], 'revenue': g['totalRev'], 'fraud': fraud})
    rows.sort(key=lambda x: x['revenue'], reverse=True)

    if not rows:
        log.info(f"No high-fraud channels found for {period}, skipping report")
        return

    total_rev = sum(r['revenue'] for r in rows)
    date_label = f"{period[:2]}-{period[2:]}"
    content_lines = format_report_content(rows, total_rev, "收入≥$100/天 且 作弊率>20%")

    msg = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"🔴 高作弊需关停渠道 | {date_label}",
                    "content": content_lines
                }
            }
        }
    }
    resp = requests.post(WEBHOOK_URL, json=msg, timeout=10)
    log.info(f"Webhook sent: {resp.status_code} {resp.text}")


# ============ 优化渠道明细推送 ============
def send_optimize_channel_report(period):
    """推送优化渠道明细：高收入包中作弊率<20%的渠道"""
    from collections import defaultdict

    content = DASHBOARD_DATA.read_text(encoding="utf-8")
    match = re.search(r'const\s+DATA\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if not match:
        log.warning("Cannot parse DATA from JS file, skipping optimize report")
        return
    data = json.loads(match.group(1))

    raw = [d for d in data if d['period'] == period]
    if not raw:
        log.warning(f"No data found for period {period}, skipping optimize report")
        return
    pub_map = dict(zip(PUBS, PUB_SHORT))

    # Step 1: find flagged packages (same as 高收入高作弊: per-channel rev>=100 & fraud>20%)
    pub_detail = defaultdict(lambda: defaultdict(lambda: {
        'package_name': '', 'totalRev': 0, 'fraudNum': 0, 'convSum': 0
    }))
    for d in raw:
        cid = d['campaign_id']
        for p in PUBS:
            rev = (d.get('pub_rev') or {}).get(p, 0)
            if rev <= 0:
                continue
            g = pub_detail[p][cid]
            g['package_name'] = d['package_name']
            g['totalRev'] += rev
            f = (d.get('pub_fraud') or {}).get(p, 0)
            g['fraudNum'] += f * d['conversions']
            g['convSum'] += d['conversions']

    flagged_pkgs = set()
    for p in PUBS:
        for cid, g in pub_detail[p].items():
            fraud = g['fraudNum'] / g['convSum'] if g['convSum'] > 0 else 0
            if g['totalRev'] >= 100 and fraud > 0.2:
                flagged_pkgs.add(g['package_name'])

    if not flagged_pkgs:
        log.info(f"No flagged packages for {period}, skipping optimize report")
        return

    # Step 2: for flagged packages, find channels with fraud < 20%
    optimize_detail = defaultdict(lambda: defaultdict(lambda: {
        'package_name': '', 'advertiser': '', 'totalRev': 0, 'fraudNum': 0, 'convSum': 0
    }))
    for d in raw:
        if d['package_name'] not in flagged_pkgs:
            continue
        cid = d['campaign_id']
        for p in PUBS:
            rev = (d.get('pub_rev') or {}).get(p, 0)
            if rev <= 0:
                continue
            g = optimize_detail[p][cid]
            g['package_name'] = d['package_name']
            g['advertiser'] = d.get('advertiser', '')
            g['totalRev'] += rev
            f = (d.get('pub_fraud') or {}).get(p, 0)
            g['fraudNum'] += f * d['conversions']
            g['convSum'] += d['conversions']

    rows = []
    for p in PUBS:
        for cid, g in optimize_detail[p].items():
            fraud = g['fraudNum'] / g['convSum'] if g['convSum'] > 0 else 0
            if fraud >= 0.2 or g['totalRev'] < 50:
                continue
            rows.append({'publisher': pub_map[p], 'package_name': g['package_name'],
                         'advertiser': g['advertiser'], 'revenue': g['totalRev'], 'fraud': fraud})
    rows.sort(key=lambda x: x['revenue'], reverse=True)

    if not rows:
        log.info(f"No optimize channels found for {period}, skipping report")
        return

    total_rev = sum(r['revenue'] for r in rows)
    date_label = f"{period[:2]}-{period[2:]}"
    content_lines = format_report_content(rows, total_rev, "高收入包中作弊率<20%的渠道")

    msg = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"🟢 可补量渠道明细 | {date_label}",
                    "content": content_lines
                }
            }
        }
    }
    resp = requests.post(WEBHOOK_URL, json=msg, timeout=10)
    log.info(f"Optimize channel webhook sent: {resp.status_code} {resp.text}")


# ============ GitHub Pages推送 ============
def push_to_github():
    """将更新后的数据文件推送到GitHub"""
    repo_dir = _DIR
    try:
        # 添加数据文件
        subprocess.run(["git", "add", "360_dashboard_data.js"], cwd=repo_dir, check=True, capture_output=True)
        # 检查是否有变更
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, capture_output=True)
        if result.returncode == 0:
            log.info("No changes to push")
            return
        # 提交
        today = datetime.now().strftime("%Y-%m-%d")
        subprocess.run(["git", "commit", "-m", f"Auto update {today}"], cwd=repo_dir, check=True, capture_output=True)
        # 推送
        subprocess.run(["git", "push"], cwd=repo_dir, check=True, capture_output=True)
        log.info("Pushed to GitHub successfully")
    except subprocess.CalledProcessError as e:
        log.error(f"Git error: {e.stderr.decode() if e.stderr else e}")


# ============ 主流程 ============
def main():
    # T-2 date
    today = datetime.now()
    t2 = today - timedelta(days=2)
    date_str = t2.strftime("%Y%m%d")
    period = t2.strftime("%m%d")
    log.info(f"=== Update started: T-2 = {date_str}, period = {period} ===")

    # Check if already exists
    existing = get_existing_periods()
    if period in existing:
        log.info(f"Period {period} already exists in data file, skipping query.")
    else:
        # Query
        token = load_token()
        rows = query_360_data(date_str, token)

        # Process
        records = process_data(rows)
        log.info(f"Processed {len(records)} campaigns")

        # Write
        append_data(records, period)
        log.info(f"=== Update complete: {len(records)} records added for {period} ===")

    # 推送T-2的高收入高作弊渠道明细到飞书群
    try:
        send_high_fraud_report(period)
    except Exception as e:
        log.error(f"Failed to send high-fraud report: {e}")

    # 推送T-2的优化渠道明细到飞书群
    try:
        send_optimize_channel_report(period)
    except Exception as e:
        log.error(f"Failed to send optimize channel report: {e}")

    # 推送到GitHub Pages
    try:
        push_to_github()
    except Exception as e:
        log.error(f"Failed to push to GitHub: {e}")


if __name__ == "__main__":
    main()
