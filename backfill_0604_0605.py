"""补0604和0605两天的数据"""
import json, sys, time, os
from pathlib import Path
import requests

sys.stdout.reconfigure(encoding='utf-8')

_DIR = Path(__file__).resolve().parent
KUBUUBI_CONFIG = Path(r"C:\Users\Mi\kyuubi-config.json")
BASE_URL = "http://proxy-service-http-alisgp0-dp.api.xiaomi.net"
PUBS = ['1000218','1000220','1000222','1000223','1000224','1000226','1000253','1000254','1000255','1000260']

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


def load_token():
    with open(KUBUUBI_CONFIG, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    tokens = cfg.get('tokens', [])
    t = tokens[0]
    return t['token'] if isinstance(t, dict) else t


def submit_sql(sql, token):
    headers = {'X-SqlProxy-User': token, 'X-SqlProxy-Engine': 'auto', 'Content-Type': 'text/plain;charset=utf-8'}
    resp = requests.post(f'{BASE_URL}/olap/api/v2/statement/query', data=sql.encode('utf-8'), headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    data = body.get('data', {})
    return data.get('queryId')


def wait_query(query_id, token, max_wait=300):
    elapsed = 0
    while elapsed < max_wait:
        headers = {'X-SqlProxy-User': token}
        resp = requests.post(f'{BASE_URL}/olap/api/v2/statement/getQueryStatus', params={'queryId': query_id}, headers=headers, timeout=30)
        body = resp.json()
        data = body.get('data', {})
        state = data.get('state', '')
        if data.get('nextQueryId'):
            query_id = data['nextQueryId']
        if state == 'FINISHED':
            return query_id
        if state in ('FAILED', 'CANCELLED'):
            raise RuntimeError(f'Query {state}')
        time.sleep(2)
        elapsed += 2
    raise RuntimeError('Query timeout')


def fetch_results(query_id, token):
    headers = {'X-SqlProxy-User': token}
    all_rows = []
    qid = query_id
    while qid:
        resp = requests.post(f'{BASE_URL}/olap/api/v2/statement/fetchResult', params={'queryId': qid}, headers=headers, timeout=60)
        body = resp.json()
        data = body.get('data', {})
        all_rows.extend(data.get('rows', []))
        qid = data.get('nextResultQueryId')
    return all_rows


def process_rows(rows):
    campaigns = {}
    for row in rows:
        cid = str(row[0])
        pub_id = str(row[1])
        if cid not in campaigns:
            campaigns[cid] = {
                'advertiser_name': row[3] or '', 'advertiser_id': row[4],
                'package_name': row[2] or '', 'total_revenue': 0, 'total_conversions': 0,
                'total_block': 0, 'total_pa': 0, 'pub_data': {}
            }
        c = campaigns[cid]
        c['total_revenue'] += row[5] or 0
        c['total_conversions'] += row[6] or 0
        c['total_block'] += row[7] or 0
        c['total_pa'] += row[8] or 0
        pub_rev = row[5] or 0
        pub_conv = row[6] or 0
        pub_block = row[7] or 0
        pub_pa = row[8] or 0
        denom = pub_block + pub_conv
        pub_fraud = (pub_pa + pub_block) / denom if denom > 0 else 0
        c['pub_data'][pub_id] = {'fraud': pub_fraud, 'revenue': pub_rev, 'conv': pub_conv, 'block': pub_block, 'pa': pub_pa}

    result = []
    for cid, c in campaigns.items():
        total_denom = c['total_block'] + c['total_conversions']
        overall_fraud = (c['total_pa'] + c['total_block']) / total_denom if total_denom > 0 else 0
        overall_block = c['total_block'] / total_denom if total_denom > 0 else 0
        overall_pa = c['total_pa'] / total_denom if total_denom > 0 else 0
        adv = c['advertiser_name'] or ''
        adv_id = c['advertiser_id']
        advertiser = f'{adv}({adv_id})' if adv_id and adv else adv
        pub_fraud, pub_rev, pub_conv, pub_block_cnt, pub_pa_cnt = {}, {}, {}, {}, {}
        for p in PUBS:
            if p in c['pub_data']:
                pub_fraud[p] = c['pub_data'][p]['fraud']
                pub_rev[p] = c['pub_data'][p]['revenue']
                pub_conv[p] = int(c['pub_data'][p]['conv'])
                pub_block_cnt[p] = int(c['pub_data'][p]['block'])
                pub_pa_cnt[p] = int(c['pub_data'][p]['pa'])
            else:
                pub_fraud[p] = 0; pub_rev[p] = 0; pub_conv[p] = 0; pub_block_cnt[p] = 0; pub_pa_cnt[p] = 0
        result.append({
            'campaign_id': cid, 'advertiser': advertiser, 'package_name': c['package_name'] or '',
            'revenue': round(c['total_revenue'], 2), 'conversions': int(c['total_conversions']),
            'overall_fraud': round(overall_fraud, 6), 'overall_block': round(overall_block, 6), 'overall_pa': round(overall_pa, 6),
            'pub_fraud': pub_fraud, 'pub_revenue': pub_rev, 'pub_rev': pub_rev,
            'pub_conv': pub_conv, 'pub_block': pub_block_cnt, 'pub_pa': pub_pa_cnt,
        })
    result.sort(key=lambda x: x['revenue'], reverse=True)
    return result


def append_to_data(records, period):
    data_path = _DIR / '360_dashboard_data.js'
    content = data_path.read_text(encoding='utf-8')
    idx = content.index('const DATA = ') + len('const DATA = ')
    data = json.loads(content[idx:].rstrip(';'))
    for r in records:
        r['period'] = period
        r['days'] = 1
    data.extend(records)
    new_content = 'const DATA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';'
    data_path.write_text(new_content, encoding='utf-8')
    return len(records)


token = load_token()

for date_str, period in [('20260604', '0604'), ('20260605', '0605')]:
    print(f'Querying {date_str}...', flush=True)
    sql = SQL_TEMPLATE.format(date=date_str)
    qid = submit_sql(sql, token)
    qid = wait_query(qid, token)
    rows = fetch_results(qid, token)
    print(f'  Got {len(rows)} rows', flush=True)
    records = process_rows(rows)
    print(f'  Processed {len(records)} campaigns', flush=True)
    n = append_to_data(records, period)
    print(f'  Appended {n} records for period {period}', flush=True)

print('Done!')
