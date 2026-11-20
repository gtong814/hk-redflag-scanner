import streamlit as st
from google import genai
from pypdf import PdfReader

st.set_page_config(page_title="公告紅旗掃描器", page_icon="🚩", layout="wide")
st.title("🚩 上市公司公告紅旗掃描器")

# 優先從 Streamlit Secrets 讀取 API Key，若未設定則可於側邊欄手動輸入
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

# 側邊欄：自訂紅旗檢查清單
st.sidebar.header("⚙️ 自訂紅旗條件")
default_flags = [
    "大幅折讓配股、供股或發行可換股債券 (CB)",
    "盈利警告 / 業績大幅倒退",
    "核數師（審計師）辭任或非標準審計意見",
    "大股東減持或核心管理層突發變動",
    "延遲刊發業績、停牌風險或重大訴訟"
]
selected_flags = st.sidebar.multiselect("監控項目：", default_flags, default=default_flags)
custom_flag = st.sidebar.text_input("新增自訂條件（選填）：")
if custom_flag:
    selected_flags.append(custom_flag)

# 主畫面：輸入公告來源
tab1, tab2 = st.tabs(["📄 上傳公告 PDF", "📝 貼上公告文字"])
announcement_text = ""

with tab1:
    uploaded_file = st.file_uploader("上傳從披露易下載的 PDF 公告", type=["pdf"])
    if uploaded_file is not None:
        reader = PdfReader(uploaded_file)
        announcement_text = "\n".join([page.extract_text() or "" for page in reader.pages])
        st.success(f"成功讀取 PDF，共 {len(reader.pages)} 頁。")

with tab2:
    pasted_text = st.text_area("直接貼上公告內容：", height=220)
    if pasted_text:
        announcement_text = pasted_text

# 執行掃描
if st.button("🔍 開始掃描紅旗", type="primary"):
    if not api_key:
        st.error("請先在側邊欄輸入 API Key，或在 Streamlit Secrets 設定 GEMINI_API_KEY。")
    elif not announcement_text.strip():
        st.warning("請先上傳 PDF 或貼上公告文字。")
    else:
        with st.spinner("AI 正在細讀公告並排查地雷..."):
            try:
                client = genai.Client(api_key=api_key)
                flags_str = "\n".join([f"- {f}" for f in selected_flags])
                prompt = f"""
你是一位專業的股票風險分析師。請閱讀以下上市公司公告，並根據「紅旗清單」排查潛在風險。

【紅旗清單】：
{flags_str}

請以繁體中文輸出以下格式：
1. **整體風險評級**：高風險 🔴 / 中風險 🟡 / 低風險 🟢
2. **觸發的紅旗項目**：列出觸發的項目並引用關鍵數據（例如折讓百分比、虧損金額、日期）。若無則寫「未發現明顯紅旗」。
3. **小股東影響摘要**：用 3 句以內的白話總結重點。

【公告內容】：
{announcement_text[:30000]}
"""
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                st.subheader("📊 掃描結果")
                st.markdown(response.text)
            except Exception as e:
                st.error(f"掃描時發生錯誤：{e}")
