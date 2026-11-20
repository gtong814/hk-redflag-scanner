import io
import json
import os
import time
from datetime import datetime, timedelta
import requests
from pypdf import PdfReader
from google import genai
from google.genai import types

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_hkex_stock_map():
    """從披露易取得 股票代號 -> 內部 stockId 對照表"""
    url = "https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_c.json"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    stock_map = {}
    for item in resp.json():
        code = str(item.get("c", "")).zfill(5)
        stock_map[code] = {"id": item.get("i"), "name": item.get("n", "")}
    return stock_map

def fetch_announcements(stock_id, days=3):
    """抓取指定股票過去 N 天的披露易公告"""
    to_date = datetime.now().strftime("%Y%m%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    url = (
        f"https://www1.hkexnews.hk/search/titleSearchServlet.do?"
        f"sortDir=0&sortByOptions=DateTime&category=0&market=SEHK"
        f"&stockId={stock_id}&documentType=-1&fromDate={from_date}&toDate={to_date}"
        f"&title=&searchType=0&t1code=-2&t2Gcode=-2&t2code=-2&rowRange=10&lang=ZH"
    )
    resp = requests.get(url, headers=HEADERS, timeout=20)
    data = resp.json()
    if not data.get("result"):
        return []
    return json.loads(data["result"])

def extract_pdf_text(file_link, max_pages=15):
    """下載 PDF 並擷取文字（限制前 15 頁以加快速度與節省 Token）"""
    pdf_url = f"https://www1.hkexnews.hk{file_link}"
    resp = requests.get(pdf_url, headers=HEADERS, timeout=30)
    reader = PdfReader(io.BytesIO(resp.content))
    text = ""
    for page in reader.pages[:max_pages]:
        text += (page.extract_text() or "") + "\n"
    return text.strip(), pdf_url

def analyze_with_gemini(client, stock_name, title, content):
    """呼叫 Gemini 進行紅旗掃描並強制回傳 JSON 格式"""
    prompt = f"""
你是專業港股風險分析師。請分析以下上市公司公告，排查潛在「紅旗」（例如：折讓配股/供股/發CB、盈利警告、核數師辭任、延遲發業績、大股東減持、高層突發變動、重大訴訟、停牌風險）。

公司：{stock_name}
公告標題：{title}
公告內容節錄：
{content[:25000]}

請嚴格以 JSON 格式回覆，包含以下欄位：
- "risk_level": 只能填 "高風險"、"中風險" 或 "低風險"
- "red_flags": 字串陣列，列出觸發的紅旗項目與關鍵數字；若無則填 ["無明顯紅旗"]
- "summary": 繁體中文，100字以內白話總結對小股東的影響
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(response.text)

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("找不到 GEMINI_API_KEY 環境變數")
    client = genai.Client(api_key=api_key)

    with open("watchlist.txt", "r", encoding="utf-8") as f:
        watchlist = [line.strip().zfill(5) for line in f if line.strip()]

    stock_map = get_hkex_stock_map()
    results = []

    for code in watchlist:
        if code not in stock_map:
            print(f"找不到股票代號：{code}")
            continue
        stock_id = stock_map[code]["id"]
        stock_name = stock_map[code]["name"]
        print(f"正在掃描：{code} {stock_name}...")

        anns = fetch_announcements(stock_id, days=3)
        for ann in anns:
            file_link = ann.get("FILE_LINK", "")
            title = ann.get("TITLE", "")
            date_time = ann.get("DATE_TIME", "")
            if not file_link.lower().endswith(".pdf"):
                continue

            try:
                text, pdf_url = extract_pdf_text(file_link)
                if len(text) < 50:
                    analysis = {
                        "risk_level": "中風險",
                        "red_flags": ["掃描版 PDF 無法直接讀取文字，建議手動查閱"],
                        "summary": "此公告可能為圖片掃描檔，請點擊連結人工確認。"
                    }
                else:
                    analysis = analyze_with_gemini(client, stock_name, title, text)

                results.append({
                    "code": code,
                    "name": stock_name,
                    "date": date_time,
                    "title": title,
                    "risk_level": analysis.get("risk_level", "低風險"),
                    "red_flags": analysis.get("red_flags", []),
                    "summary": analysis.get("summary", ""),
                    "pdf_url": pdf_url
                })
                time.sleep(2)  # 避免觸發 API 頻率限制
            except Exception as e:
                print(f"處理 {code} 公告時出錯：{e}")

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S (UTC)"),
        "data": results
    }
    with open("scan_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"掃描完成，共處理 {len(results)} 份公告。")

if __name__ == "__main__":
    main()
