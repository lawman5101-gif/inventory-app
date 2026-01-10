import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
from io import BytesIO
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# PDF(결재용)
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(page_title="환경미화 소모품 스마트 장부", layout="wide")

# =========================================================
# 로고/헤더/푸터 UI
# - 로고 파일: assets/court_logo.png
# - 하단 왼쪽: 만든이 오장일
# =========================================================
LOGO_PATH = Path("assets/court_logo.png")

# 헤더
c1, c2 = st.columns([1.2, 10])
with c1:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=78)
    else:
        st.warning("로고 파일이 없습니다: assets/court_logo.png")

with c2:
    st.markdown(
        """
        <div style="display:flex; flex-direction:column; justify-content:center; height:78px;">
          <div style="font-size:28px; font-weight:800; margin:0; padding:0;">대구고등법원</div>
          <div style="font-size:15px; color:#666; margin-top:2px;">환경미화 소모품 스마트 장부</div>
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()

# 푸터(고정)
st.markdown(
    """
    <style>
      .footer-left {
        position: fixed;
        left: 16px;
        bottom: 10px;
        font-size: 12px;
        color: #888;
        z-index: 9999;
      }
    </style>
    <div class="footer-left">만든이: 오장일</div>
    """,
    unsafe_allow_html=True
)

# =========================================================
# Secrets(권장): Streamlit Cloud Settings -> Secrets
# =========================================================
ADMIN_PASSWORD = st.secrets.get("app", {}).get("admin_password", "1234")
ORG_NAME = st.secrets.get("app", {}).get("org_name", "대구고등법원")
DEPT_NAME = st.secrets.get("app", {}).get("dept_name", "환경미화")
APPROVERS = st.secrets.get("app", {}).get("approvers", "담당,계장,과장").split(",")

SPREADSHEET_NAME = st.secrets["gsheets"]["spreadsheet_name"]  # 필수

# =========================================================
# (선택) 결재용 PDF 한글 폰트
# - repo에 fonts/NotoSansKR-Regular.ttf 올리면 자동 적용
# =========================================================
def register_korean_font():
    font_path = "fonts/NotoSansKR-Regular.ttf"
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont("NotoSansKR", font_path))
        return "NotoSansKR"
    return "Helvetica"

PDF_FONT = register_korean_font()

# =========================================================
# Google Sheets 연결
# =========================================================
def gs_client():
    info = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def gs_open():
    gc = gs_client()
    return gc.open(SPREADSHEET_NAME)

def get_ws(sh, name):
    try:
        return sh.worksheet(name)
    except Exception:
        return sh.add_worksheet(title=name, rows=2000, cols=20)

def ensure_headers():
    sh = gs_open()
    ws_logs = get_ws(sh, "logs")
    ws_r = get_ws(sh, "recipients")
    ws_i = get_ws(sh, "items")

    if ws_logs.row_values(1) != ["시간", "수령자", "품목", "수량", "비고"]:
        ws_logs.clear()
        ws_logs.append_row(["시간", "수령자", "품목", "수량", "비고"])

    if ws_r.row_values(1) != ["이름", "활성"]:
        ws_r.clear()
        ws_r.append_row(["이름", "활성"])

    if ws_i.row_values(1) != ["품목명", "활성"]:
        ws_i.clear()
        ws_i.append_row(["품목명", "활성"])

    return ws_logs, ws_r, ws_i

ws_logs, ws_r, ws_i = ensure_headers()

def ws_to_df(ws):
    values = ws.get_all_values()
    if len(values) <= 1:
        return pd.DataFrame(columns=values[0] if values else [])
    header = values[0]
    rows = values[1:]
    return pd.DataFrame(rows, columns=header)

def get_active_lists():
    df_r = ws_to_df(ws_r)
    df_i = ws_to_df(ws_i)

    recipients = []
    items = []

    if not df_r.empty:
        df_r["활성"] = df_r["활성"].astype(str)
        recipients = sorted(df_r[df_r["활성"] == "1"]["이름"].dropna().astype(str).tolist())

    if not df_i.empty:
        df_i["활성"] = df_i["활성"].astype(str)
        items = sorted(df_i[df_i["활성"] == "1"]["품목명"].dropna().astype(str).tolist())

    return recipients, items

def append_log(recipient, item, qty, note):
    ws_logs.append_row(
        [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), recipient, item, str(int(qty)), note or ""],
        value_input_option="USER_ENTERED"
    )

def load_logs_df():
    df = ws_to_df(ws_logs)
    if df.empty:
        return df
    df["시간"] = pd.to_datetime(df["시간"], errors="coerce")
    df["수량"] = pd.to_numeric(df["수량"], errors="coerce").fillna(0).astype(int)
    return df.dropna(subset=["시간"])

# =========================================================
# 초기 시딩(한 번만): recipients/items 시트가 비어있을 때만 채움
# =========================================================
DEFAULT_RECIPIENTS = [
    "김순영","노나경","김감열","임금란","최점순","최명숙","김상임","김일란",
    "정정화","이순옥","김영경","정해동","박선옥","박영순","우미진","우시은",
    "장기현","박심옥"
]
DEFAULT_ITEMS = [
    "핸드타올","점보롤",
    "락스","박리제","왁스","물비누","소독제","세수비누","빨래비누","하이타이",
    "쓰레기봉투(100L)","쓰레기봉투(75L)","쓰레기봉투(50L)","쓰레기봉투(20L)",
    "고무장갑","장갑","수세미(녹색)","수세미(철)","극세사수건","마대걸레","기름걸레",
    "갈대빗자루","플라스틱빗자루","쓰레받이(대)","쓰레받이(소)",
    "빠께스","변기솔","금속광택제","바가지",
    "위생비닐","위생봉투컵","검정비닐","헤라"
]

def seed_lists_once():
    df_r = ws_to_df(ws_r)
    df_i = ws_to_df(ws_i)

    if df_r.empty:
        for n in DEFAULT_RECIPIENTS:
            ws_r.append_row([n, "1"])

    if df_i.empty:
        for n in DEFAULT_ITEMS:
            ws_i.append_row([n, "1"])

seed_lists_once()

# =========================================================
# 월말 장부(Excel)
# =========================================================
def build_month_excel(df_month: pd.DataFrame, ym: str) -> BytesIO:
    df_month = df_month.copy().sort_values("시간")
    item_sum = df_month.groupby("품목")["수량"].sum().sort_values(ascending=False).reset_index()
    recip_sum = df_month.groupby("수령자")["수량"].sum().sort_values(ascending=False).reset_index()
    pivot = df_month.pivot_table(index="수령자", columns="품목", values="수량", aggfunc="sum", fill_value=0)

    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_month[["시간","수령자","품목","수량","비고"]].to_excel(writer, index=False, sheet_name=f"{ym}_원장")
        item_sum.to_excel(writer, index=False, sheet_name=f"{ym}_품목합계")
        recip_sum.to_excel(writer, index=False, sheet_name=f"{ym}_수령자합계")
        pivot.to_excel(writer, sheet_name=f"{ym}_교차표")
    out.seek(0)
    return out

# =========================================================
# 결재용 PDF 생성
# =========================================================
def build_approval_pdf(df_month: pd.DataFrame, ym: str) -> BytesIO:
    df_month = df_month.copy().sort_values("시간")
    item_sum = df_month.groupby("품목")["수량"].sum().sort_values(ascending=False).reset_index()
    recip_sum = df_month.groupby("수령자")["수량"].sum().sort_values(ascending=False).reset_index()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)

    styles = getSampleStyleSheet()
    styles["Normal"].fontName = PDF_FONT
    styles["Title"].fontName = PDF_FONT
    styles["Heading2"].fontName = PDF_FONT

    story = []

    title = f"{ORG_NAME} {DEPT_NAME} 소모품 지급 월말 결재자료 ({ym})"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 12))

    # 결재란
    approver_row = [["구분"] + APPROVERS]
    approver_row.append(["서명"] + [""] * len(APPROVERS))
    t = Table(approver_row, colWidths=[50] + [((A4[0]-56-50)/len(APPROVERS))]*len(APPROVERS))
    t.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), PDF_FONT, 10),
        ("GRID", (0,0), (-1,-1), 0.7, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWHEIGHT", (0,1), (-1,1), 28),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # 요약
    story.append(Paragraph("1. 월간 요약", styles["Heading2"]))
    story.append(Spacer(1, 6))
    total_qty = int(df_month["수량"].sum())
    story.append(Paragraph(f"• 총 지급 건수: {len(df_month)}건", styles["Normal"]))
    story.append(Paragraph(f"• 총 지급 수량: {total_qty}", styles["Normal"]))
    story.append(Spacer(1, 10))

    # 품목 합계
    story.append(Paragraph("2. 품목별 합계", styles["Heading2"]))
    story.append(Spacer(1, 6))
    item_table_data = [["품목", "합계"]] + item_sum.values.tolist()
    item_table = Table(item_table_data, colWidths=[360, 120])
    item_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), PDF_FONT, 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 12))

    # 수령자 합계
    story.append(Paragraph("3. 수령자별 합계", styles["Heading2"]))
    story.append(Spacer(1, 6))
    recip_table_data = [["수령자", "합계"]] + recip_sum.values.tolist()
    recip_table = Table(recip_table_data, colWidths=[360, 120])
    recip_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), PDF_FONT, 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
    ]))
    story.append(recip_table)
    story.append(PageBreak())

    # 원장(장부)
    story.append(Paragraph("4. 월간 지급 원장(장부)", styles["Heading2"]))
    story.append(Spacer(1, 6))
    ledger = df_month[["시간","수령자","품목","수량","비고"]].copy()
    ledger["시간"] = ledger["시간"].dt.strftime("%Y-%m-%d %H:%M")
    ledger_data = [["시간", "수령자", "품목", "수량", "비고"]] + ledger.values.tolist()

    ledger_table = Table(ledger_data, colWidths=[110, 70, 170, 50, 120], repeatRows=1)
    ledger_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), PDF_FONT, 8),
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN", (3,1), (3,-1), "RIGHT"),
    ]))
    story.append(ledger_table)

    doc.build(story)
    buf.seek(0)
    return buf

# =========================================================
# 메뉴
# =========================================================
menu = st.sidebar.radio("메뉴", ["📤 지급 입력", "📊 통계", "📁 월말 장부 출력", "⚙️ 관리자"])

# =========================================================
# 1) 지급 입력
# =========================================================
if menu == "📤 지급 입력":
    st.subheader("📤 소모품 지급 입력")

    recipients, items = get_active_lists()
    if not recipients:
        st.error("활성 수령자 목록이 비어 있습니다. 관리자 메뉴에서 등록하세요.")
        st.stop()
    if not items:
        st.error("활성 품목 목록이 비어 있습니다. 관리자 메뉴에서 등록하세요.")
        st.stop()

    with st.form("issue_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2,2,1])
        with c1:
            recip = st.selectbox("수령자", recipients)
        with c2:
            item = st.selectbox("품목", items)
        with c3:
            qty = st.number_input("수량", min_value=1, value=1, step=1)

        note = st.text_input("비고(선택)", placeholder="예: 대청소, 특별작업 등")
        ok = st.form_submit_button("✅ 저장")

        if ok:
            append_log(recip, item, qty, note)
            st.success("저장되었습니다.")

    st.divider()
    st.caption("최근 50건")
    df = load_logs_df()
    if df.empty:
        st.info("아직 기록이 없습니다.")
    else:
        st.dataframe(df.head(50), use_container_width=True)

# =========================================================
# 2) 통계
# =========================================================
elif menu == "📊 통계":
    st.subheader("📊 월별 통계")

    df = load_logs_df()
    if df.empty:
        st.info("통계를 낼 데이터가 없습니다.")
        st.stop()

    df["월"] = df["시간"].dt.to_period("M").astype(str)
    ym = st.selectbox("월 선택", sorted(df["월"].unique()))
    mdf = df[df["월"] == ym].copy()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 품목별 총 소모량")
        s1 = mdf.groupby("품목")["수량"].sum().reset_index().sort_values("수량", ascending=False)
        ch1 = alt.Chart(s1).mark_bar().encode(
            x=alt.X("수량:Q", title="총 수량"),
            y=alt.Y("품목:N", sort="-x"),
            tooltip=["품목","수량"]
        )
        st.altair_chart(ch1, use_container_width=True)
        st.dataframe(s1, use_container_width=True)

    with c2:
        st.markdown("### 수령자별 총 소모량")
        s2 = mdf.groupby("수령자")["수량"].sum().reset_index().sort_values("수량", ascending=False)
        ch2 = alt.Chart(s2).mark_bar().encode(
            x=alt.X("수량:Q", title="총 수량"),
            y=alt.Y("수령자:N", sort="-x"),
            tooltip=["수령자","수량"]
        )
        st.altair_chart(ch2, use_container_width=True)
        st.dataframe(s2, use_container_width=True)

# =========================================================
# 3) 월말 장부 출력 (Excel + 결재용 PDF)
# =========================================================
elif menu == "📁 월말 장부 출력":
    st.subheader("📁 월말 장부 출력 (Excel + 결재용 PDF)")

    df = load_logs_df()
    if df.empty:
        st.info("출력할 데이터가 없습니다.")
        st.stop()

    df["월"] = df["시간"].dt.to_period("M").astype(str)
    ym = st.selectbox("출력 월 선택", sorted(df["월"].unique()))

    mdf = df[df["월"] == ym].copy()
    if mdf.empty:
        st.info("해당 월 데이터가 없습니다.")
        st.stop()

    st.caption(f"{ym} / {len(mdf)}건")
    st.dataframe(mdf.sort_values("시간"), use_container_width=True)

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        excel_bytes = build_month_excel(mdf, ym)
        st.download_button(
            "⬇️ 월말 장부(Excel) 다운로드",
            data=excel_bytes,
            file_name=f"{ym}_환경미화_소모품_월말장부.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with col2:
        pdf_bytes = build_approval_pdf(mdf, ym)
        st.download_button(
            "⬇️ 결재용 PDF 다운로드",
            data=pdf_bytes,
            file_name=f"{ym}_환경미화_소모품_결재자료.pdf",
            mime="application/pdf"
        )

    if PDF_FONT == "Helvetica":
        st.warning("⚠️ 결재용 PDF에서 한글이 □로 보이면, repo에 fonts/NotoSansKR-Regular.ttf를 추가해 주세요.")

# =========================================================
# 4) 관리자: 명단/품목 관리(추가/비활성화)
# =========================================================
elif menu == "⚙️ 관리자":
    st.subheader("⚙️ 관리자")
    pw = st.text_input("관리자 비밀번호", type="password")
    if pw != ADMIN_PASSWORD:
        st.warning("관리자 비밀번호를 입력하세요.")
        st.stop()

    st.success("관리자 인증 완료")

    tab1, tab2 = st.tabs(["수령자 관리", "품목 관리"])

    def update_ws_from_df(ws, df):
        ws.clear()
        ws.append_row(df.columns.tolist())
        ws.append_rows(df.astype(str).values.tolist(), value_input_option="USER_ENTERED")

    with tab1:
        st.markdown("### 수령자 관리")
        df_r = ws_to_df(ws_r)
        if df_r.empty:
            df_r = pd.DataFrame(columns=["이름","활성"])
        st.dataframe(df_r, use_container_width=True)

        new_names = st.text_area("수령자 추가(한 줄에 한 명)", height=100)
        if st.button("➕ 수령자 추가"):
            lines = [x.strip() for x in new_names.splitlines() if x.strip()]
            for n in lines:
                ws_r.append_row([n, "1"])
            st.success("추가 완료")
            st.rerun()

        st.markdown("#### 비활성/활성 전환")
        target = st.selectbox("대상(이름)", sorted(df_r["이름"].astype(str).unique()) if not df_r.empty else [])
        action = st.radio("처리", ["비활성화", "활성화"], horizontal=True)
        if st.button("적용"):
            df_r["이름"] = df_r["이름"].astype(str)
            df_r.loc[df_r["이름"] == target, "활성"] = "0" if action == "비활성화" else "1"
            update_ws_from_df(ws_r, df_r)
            st.success("적용 완료")
            st.rerun()

    with tab2:
        st.markdown("### 품목 관리")
        df_i = ws_to_df(ws_i)
        if df_i.empty:
            df_i = pd.DataFrame(columns=["품목명","활성"])
        st.dataframe(df_i, use_container_width=True)

        new_items = st.text_area("품목 추가(한 줄에 한 품목)", height=100)
        if st.button("➕ 품목 추가"):
            lines = [x.strip() for x in new_items.splitlines() if x.strip()]
            for it in lines:
                ws_i.append_row([it, "1"])
            st.success("추가 완료")
            st.rerun()

        st.markdown("#### 비활성/활성 전환")
        target = st.selectbox("대상(품목명)", sorted(df_i["품목명"].astype(str).unique()) if not df_i.empty else [])
        action = st.radio("처리", ["비활성화", "활성화"], horizontal=True, key="item_act")
        if st.button("적용", key="item_apply"):
            df_i["품목명"] = df_i["품목명"].astype(str)
            df_i.loc[df_i["품목명"] == target, "활성"] = "0" if action == "비활성화" else "1"
            update_ws_from_df(ws_i, df_i)
            st.success("적용 완료")
            st.rerun()
