import io
import json
import os
import re
from datetime import datetime, timedelta
import pandas as pd
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 高風險紅旗關鍵字（直接標記 🔴）
HIGH_RISK_KEYWORDS = [
    "盈利警告", "盈警", "虧損", "配售", "供股", "折讓", "可換股",
    "核數師", "審計師", "辭任", "罷免", "停牌", "暫停買賣",
    "清盤", "呈請", "違約", "無法表示意見", "保留意見"
]

# 中風險留意關鍵字（標記 🟡）
MEDIUM_RISK_KEYWORDS = [
    "延遲", "訴訟", "減持", "內幕消息", "關連交易", "非常重大出售", "調查"
]


def get_ggt_list():
    """自動獲取最新港股通名單"""
    cache_file = "ggt_list.json"

    try:
        url = "https://www.szse.cn/api/report/ShowReport?SHOWTYPE=xlsx&CATALOGID=SGT_GGTBDQD&TABKEY=tab1"
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        df = pd.read_excel(io.BytesIO(resp.content), dtype=str)
        code_col = next((c for c in df.columns if "代码" in str(c) or "代碼" in str(c)), df.columns[0])
        codes = sorted(set(
            re.sub(r"\D", "", str(x)).zfill(5)
            for x in df[code_col].dropna()
            if re.sub(r"\D", "", str(x))
        ))
        if len(codes) > 300:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(codes, f, ensure_ascii=False)
            print(f"成功從深交所更新港股通名單，共 {len(codes)} 隻股票。")
            return set(codes)
    except Exception as e:
        print(f"深交所名單讀取失敗，嘗試備援來源：{e}")

    try:
        import akshare as ak
        df = ak.stock_hk_ggt_components_em()
        codes = sorted(set(str(x).zfill(5) for x in df["代码"].dropna()))
        if len(codes) > 100:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(codes, f, ensure_ascii=False)
            print(f"成功從 akshare 更新港股通名單，共 {len(codes)} 隻股票。")
            return set(codes)
    except Exception as e:
        print(f"akshare 名單讀取失敗：{e}")

    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            codes = json.load(f)
        print(f"使用本地快取港股通名單，共 {len(codes)} 隻股票。")
        return set(codes)

    raise RuntimeError("無法取得港股通名單。")


def fetch_latest_market_announcements(days=2, row_range=800):
    """一次抓取披露易全市場過去 N 天的最新公告"""
    to_date = datetime.now().strftime("%Y%m%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    url = (
        f"https://www1.hkexnews.hk/search/titleSearchServlet.do?"
        f"sortDir=0&sortByOptions=DateTime&category=0&market=SEHK"
        f"&stockId=-1&documentType=-1&fromDate={from_date}&toDate={to_date}"
        f"&title=&searchType=0&t1code=-2&t2Gcode=-2&t2code=-2&rowRange={row_range}&lang=ZH"
    )
    resp = requests.get(url, headers=HEADERS, timeout=30)
    data = resp.json()
    if not data.get("result"):
        return []
    return json.loads(data["result"])


def main():
    ggt_set = get_ggt_list()
    all_anns = fetch_latest_market_announcements(days=2, row_range=800)
    print(f"披露易共抓取 {len(all_anns)} 份最新全市場公告，開始篩選港股通紅旗...")

    results = []
    for ann in all_anns:
        raw_codes = str(ann.get("STOCK_CODE", "")).replace("<br/>", ",").split(",")
        matched_codes = [c.strip().zfill(5) for c in raw_codes if c.strip().zfill(5) in ggt_set]
        if not matched_codes:
            continue

        title = ann.get("TITLE", "")
        file_link = ann.get("FILE_LINK", "")
        if not file_link.lower().endswith(".pdf"):
            continue

        hit_high = [kw for kw in HIGH_RISK_KEYWORDS if kw in title]
        hit_med = [kw for kw in MEDIUM_RISK_KEYWORDS if kw in title]

        if not hit_high and not hit_med:
            continue

        risk_level = "高風險" if hit_high else "中風險"
        hit_all = hit_high + hit_med

        results.append({
            "code": matched_codes[0],
            "name": str(ann.get("STOCK_NAME", "")).replace("<br/>", " / "),
            "date": ann.get("DATE_TIME", ""),
            "title": title,
            "risk_level": risk_level,
            "red_flags": [f"標題命中：{kw}" for kw in hit_all],
            "summary": "（免 API Key 模式）已依紅旗關鍵字自動標記，請點擊下方按鈕直接查閱披露易原文 PDF。",
            "pdf_url": f"https://www1.hkexnews.hk{file_link}"
        })

    # 高風險排在最前面
    results.sort(key=lambda x: 0 if x["risk_level"] == "高風險" else 1)

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S (UTC)"),
        "ggt_count": len(ggt_set),
        "scanned_market_anns": len(all_anns),
        "data": results
    }
    with open("scan_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"掃描完成，共抓出 {len(results)} 份港股通紅旗公告。")


if __name__ == "__main__":
    main()
