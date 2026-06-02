"""
批量从AF获取所有包的点击/收入/激活数据，按adset(publisher)维度。
包名列表从postback表查询结果获取，用Playwright加载cookie后在浏览器内fetch AF API。
"""
import json
import sys
import io
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

AUTH_STATE = Path(r"C:\Users\Mi\af_monitor\af_monitor\config\.auth_state.json")
PACKAGES_FILE = Path(r"C:\Users\Mi\360_dashboard\postback_packages.json")
OUTPUT_FILE = Path(r"C:\Users\Mi\360_dashboard\af_data_0526_0527.json")

JS_FETCH = """async ([widget, body]) => {
    const resp = await fetch('/platform/dashboard?widget=' + widget, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        credentials: 'include',
        body: JSON.stringify(body)
    });
    const text = await resp.text();
    return {status: resp.status, body: text};
}"""

METRICS = [
    {"metric-id": "clicks", "filters": {}, "granularity": "", "category": "core",
     "period": "", "platform-id": "clicks", "attribution-source": "",
     "sort-by": {"order": "desc", "priority": 0}},
    {"metric-id": "installs", "filters": {}, "attribution-source": "appsflyer",
     "granularity": "", "category": "core", "period": "",
     "sort-by": {"order": "desc", "priority": 1}, "platform-id": "installs"},
    {"metric-id": "revenue", "filters": {}, "attribution-source": "appsflyer",
     "aggregation-type": "cumulative", "granularity": "", "category": "core",
     "period": "ltv", "platform-id": "revenue_ltv",
     "sort-by": {"order": "desc", "priority": 2}},
]


def load_packages():
    with open(PACKAGES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


async def fetch_app_data(page, app_id, start_date, end_date):
    body = {
        "dates": {"start": start_date, "end": end_date},
        "filters": {"app-id": [app_id]},
        "view-type": "ua",
        "localization": {"timezone": "UTC", "currency": "USD"},
        "groupings": [{"dimension": "adset", "limit": 500}],
        "summations": ["totals", "others"],
        "metrics": METRICS,
        "format": "json",
        "granularity": "days",
    }
    try:
        result = await page.evaluate(JS_FETCH, ["platform-widget:13", body])
        if result["status"] == 200:
            return json.loads(result["body"])
        else:
            return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None


def parse_af_data(data):
    result = {}
    if not data or "data" not in data:
        return result
    for item in data["data"]:
        adset = item.get("adset", "__unknown__")
        if adset in ("None", "__totals__", "{siteName}", "mi"):
            continue
        if adset not in result:
            result[adset] = {"clicks": 0, "installs": 0, "revenue": 0}
        result[adset]["clicks"] += item.get("clicks", 0) or 0
        result[adset]["installs"] += item.get("installs", 0) or 0
        result[adset]["revenue"] += (item.get("revenue_ltv", 0) or item.get("revenue", 0) or 0)
    return result


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-05-26")
    parser.add_argument("--end", default="2026-05-27")
    args = parser.parse_args()
    start_date = args.start
    end_date = args.end

    global OUTPUT_FILE
    OUTPUT_FILE = Path(rf"C:\Users\Mi\360_dashboard\af_data_{start_date.replace('-','')}_{end_date.replace('-','')}.json")

    packages = load_packages()
    print(f"=== AF批量取数 (Playwright): {start_date} ~ {end_date} ===")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"共 {len(packages)} 个包待查询\n")

    # Load existing results if any (resume support)
    existing = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"已有 {len(existing)} 个包的历史结果，跳过已查询的\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(AUTH_STATE),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("建立AF session...")
        await page.goto("https://hq1.appsflyer.com/apps/myapps", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)

        if "auth/login" in page.url:
            print("[ERROR] Cookie已过期，请重新登录AF")
            await browser.close()
            return

        print("登录状态有效\n")

        all_results = dict(existing)
        queried = 0
        found = 0

        for i, app_id in enumerate(packages):
            if app_id in all_results:
                continue

            data = await fetch_app_data(page, app_id, start_date, end_date)
            queried += 1

            if data and "data" in data:
                parsed = parse_af_data(data)
                if parsed:
                    all_results[app_id] = parsed
                    found += 1
                    total_c = sum(v["clicks"] for v in parsed.values())
                    total_i = sum(v["installs"] for v in parsed.values())
                    total_r = sum(v["revenue"] for v in parsed.values())
                    print(f"[{i+1}/{len(packages)}] {app_id}: clicks={total_c:,}, installs={total_i:,}, rev=${total_r:,.2f}")
                else:
                    all_results[app_id] = {}
            else:
                all_results[app_id] = {}

            # Save every 20 queries
            if queried % 20 == 0:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)
                print(f"  --- 已保存 checkpoint ({found} 个有数据 / {queried} 个已查询) ---")

        await browser.close()

    # Final save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完成 ===")
    print(f"查询: {queried} 个, 有数据: {found} 个, 总计: {len(all_results)} 个")
    print(f"数据已保存到: {OUTPUT_FILE}")

    # Summary of apps with data
    apps_with_data = {k: v for k, v in all_results.items() if v}
    print(f"\n有数据的包 ({len(apps_with_data)} 个):")
    for app_id, app_data in sorted(apps_with_data.items(), key=lambda x: sum(v["revenue"] for v in x[1].values()), reverse=True):
        total_c = sum(v["clicks"] for v in app_data.values())
        total_i = sum(v["installs"] for v in app_data.values())
        total_r = sum(v["revenue"] for v in app_data.values())
        ch = len(app_data)
        print(f"  {app_id}: {ch}渠道, clicks={total_c:,}, installs={total_i:,}, rev=${total_r:,.2f}")


if __name__ == "__main__":
    asyncio.run(main())
