import json
import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="港股披露易紅旗掃描器", page_icon="🚩", layout="wide")
st.title("🚩 港股通・披露易公告紅旗 Dashboard")

DATA_FILE = "scan_results.json"

if not os.path.exists(DATA_FILE):
    st.info("尚未有掃描紀錄。請先到 GitHub 的 Actions 分頁執行一次掃描。")
    st.stop()

with open(DATA_FILE, "r", encoding="utf-8") as f:
    payload = json.load(f)

st.caption(
    f"最後自動更新時間：{payload.get('updated_at', '未知')} ｜ "
    f"監控標的數：{payload.get('ggt_count', '未知')} ｜ "
    f"已掃描全市場公告數：{payload.get('scanned_market_anns', '未知')}"
)
records = payload.get("data", [])

if not records:
    st.success("過去 2 天內，監控名單沒有觸發紅旗關鍵字的公告。")
    st.stop()

df = pd.DataFrame(records)

# 頂部風險統計卡片
col1, col2, col3 = st.columns(3)
col1.metric("📄 紅旗公告總數", len(df))
col2.metric("🔴 高風險警報", len(df[df["risk_level"] == "高風險"]))
col3.metric("🟡 中風險留意", len(df[df["risk_level"] == "中風險"]))

st.divider()

# 側邊欄篩選與搜尋
st.sidebar.header("🔍 篩選條件")
search_query = st.sidebar.text_input("搜尋股票代號或名稱（例如 00700）：")
risk_options = df["risk_level"].unique().tolist()
risk_filter = st.sidebar.multiselect("風險等級：", risk_options, default=risk_options)

filtered_df = df[df["risk_level"].isin(risk_filter)]
if search_query:
    filtered_df = filtered_df[
        filtered_df["code"].str.contains(search_query, case=False, na=False) |
        filtered_df["name"].str.contains(search_query, case=False, na=False) |
        filtered_df["title"].str.contains(search_query, case=False, na=False)
    ]

# 逐項卡片展示
for _, row in filtered_df.iterrows():
    badge = "🔴" if row["risk_level"] == "高風險" else ("🟡" if row["risk_level"] == "中風險" else "🟢")
    with st.expander(
        f"{badge} [{row['risk_level']}] {row['code']} {row['name']} ｜ {row['title']} ({row['date']})",
        expanded=(row["risk_level"] == "高風險")
    ):
        st.markdown(f"**🚩 觸發紅旗：** {'、'.join(row['red_flags'])}")
        st.markdown(f"**📝 說明：** {row['summary']}")
        st.link_button("📄 開啟披露易原文 PDF", row["pdf_url"])
