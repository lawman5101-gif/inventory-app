import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import altair as alt
from io import BytesIO
from pathlib import Path
from typing import Optional, List, Tuple

# =========================================================
# 설정
# =========================================================
st.set_page_config(page_title="대구고등법원 환경미화 소모품 스마트 장부", layout="wide")
st.title("📱 대구고등법원 환경미화 소모품 스마트 장부")
st.caption("만든이 오장일")

DB_PATH = Path("inventory.db")

# ⚠️ 실무 운영 시 비밀번호는 반드시 변경하세요.
# 더 안전하게 하려면 Streamlit Cloud의 Secrets로 옮기는 것을 권장합니다.
ADMIN_PASSWORD = "1234"

# =========================================================
# 초기 데이터 (명단/품목)
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

# =========================================================
# DB 유틸
# =========================================================
def run(query: str, params=(), fetch: bool = False):
    # Streamlit rerun 환경에서 안전하게
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall() if fetch else None
        conn.commit()
        return rows
    finally:
        conn.close()

def init_db():
    run("""
        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            recipient_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            note TEXT,
            FOREIGN KEY(recipient_id) REFERENCES recipients(id),
            FOREIGN KEY(item_id) REFERENCES items(id)
        )
    """)

def seed_if_empty():
    r_cnt = run("SELECT COUNT(*) FROM recipients", fetch=True)[0][0]
    i_cnt = run("SELECT COUNT(*) FROM items", fetch=True)[0][0]

    if r_cnt == 0:
        for name in DEFAULT_RECIPIENTS:
            run("INSERT OR IGNORE INTO recipients(name, active) VALUES (?, 1)", (name,))
    if i_cnt == 0:
        for name in DEFAULT_ITEMS:
            run("INSERT OR IGNORE INTO items(name, active) VALUES (?, 1)", (name,))

def get_active_recipients() -> List[Tuple[int, str]]:
    return run("SELECT id, name FROM recipients WHERE active=1 ORDER BY name", fetch=True)

def get_active_items() -> List[Tuple[int, str]]:
    return run("SELECT id, name FROM items WHERE active=1 ORDER BY name", fetch=True)

def get_all_recipients():
    return run("SELECT id, name, active FROM recipients ORDER BY name", fetch=True)

def get_all_items():
    return run("SELECT id, name, active FROM items ORDER BY name", fetch=True)

def insert_log(ts: datetime, recipient_id: int, item_id: int, qty: int, note: Optional[str]):
    run(
        "INSERT INTO logs(ts, recipient_id, item_id, qty, note) VALUES (?, ?, ?, ?, ?)",
        (ts.strftime("%Y-%m-%d %H:%M:%S"), recipient_id, item_id, qty, note)
    )

def read_logs(
    start: Optional[date] = None,
    end: Optional[date] = None,
    recipient_id: Optional[int] = None,
    item_id: Optional[int] = None
) -> pd.DataFrame:
    where = []
    params = []

    if start:
        where.append("date(ts) >= date(?)")
        params.append(start.strftime("%Y-%m-%d"))
    if end:
        where.append("date(ts) <= date(?)")
        params.append(end.strftime("%Y-%m-%d"))
    if recipient_id:
        where.append("recipient_id = ?")
        params.append(recipient_id)
    if item_id:
        where.append("item_id = ?")
        params.append(item_id)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = run(f"""
        SELECT
            l.id,
            l.ts,
            r.name AS recipient,
            i.name AS item,
            l.qty,
            COALESCE(l.note, '') AS note
        FROM logs l
        JOIN recipients r ON r.id = l.recipient_id
        JOIN items i ON i.id = l.item_id
        {where_sql}
        ORDER BY l.ts DESC
    """, tuple(params), fetch=True)

    df = pd.DataFrame(rows, columns=["id", "시간", "수령자", "품목", "수량", "비고"])
    if not df.empty:
        df["시간"] = pd.to_datetime(df["시간"], errors="coerce")
    return df

def deactivate_recipient(recipient_id: int):
    run("UPDATE recipients SET active=0 WHERE id=?", (recipient_id,))

def activate_recipient(recipient_id: int):
    run("UPDATE recipients SET active=1 WHERE id=?", (recipient_id,))

def deactivate_item(item_id: int):
    run("UPDATE items SET active=0 WHERE id=?", (item_id,))

def activate_item(item_id: int):
    run("UPDATE items SET active=1 WHERE id=?", (item_id,))

def add_recipients(names: List[str]):
    for n in names:
        n = n.strip()
        if n:
            run("INSERT OR IGNORE INTO recipients(name, active) VALUES (?, 1)", (n,))

def add_items(names: List[str]):
    for n in names:
        n = n.strip()
        if n:
            run("INSERT OR IGNORE INTO items(name, active) VALUES (?, 1)", (n,))

def delete_log(log_id: int):
    run("DELETE FROM logs WHERE id=?", (log_id,))

# ====== 추가: 수정/완전삭제 유틸 ======
def update_recipient_name(recipient_id: int, new_name: str):
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("이름이 비어있습니다.")
    run("UPDATE recipients SET name=? WHERE id=?", (new_name, recipient_id))

def update_item_name(item_id: int, new_name: str):
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("품목명이 비어있습니다.")
    run("UPDATE items SET name=? WHERE id=?", (new_name, item_id))

def hard_delete_recipient(recipient_id: int):
    cnt = run("SELECT COUNT(*) FROM logs WHERE recipient_id=?", (recipient_id,), fetch=True)[0][0]
    if cnt > 0:
        raise ValueError(f"이 수령자는 지급 기록 {cnt}건이 연결되어 있어 완전 삭제할 수 없습니다. 비활성화를 사용하세요.")
    run("DELETE FROM recipients WHERE id=?", (recipient_id,))

def hard_delete_item(item_id: int):
    cnt = run("SELECT COUNT(*) FROM logs WHERE item_id=?", (item_id,), fetch=True)[0][0]
    if cnt > 0:
        raise ValueError(f"이 품목은 지급 기록 {cnt}건이 연결되어 있어 완전 삭제할 수 없습니다. 비활성화를 사용하세요.")
    run("DELETE FROM items WHERE id=?", (item_id,))

# =========================================================
# 앱 시작: DB 준비
# =========================================================
init_db()
seed_if_empty()

# =========================================================
# 메뉴
# =========================================================
menu = st.sidebar.radio("메뉴", ["📤 지급 기록", "📊 통계", "📁 내역 조회/다운로드", "⚙️ 관리자"])

# =========================================================
# 1) 지급 기록
# =========================================================
if menu == "📤 지급 기록":
    st.subheader("📤 소모품 지급 입력")

    recipients = get_active_recipients()
    items = get_active_items()

    if not recipients:
        st.error("활성 수령자가 없습니다. 관리자 메뉴에서 수령자를 등록/활성화하세요.")
        st.stop()
    if not items:
        st.error("활성 품목이 없습니다. 관리자 메뉴에서 품목을 등록/활성화하세요.")
        st.stop()

    recip_labels = [name for _id, name in recipients]
    recip_map = {name: _id for _id, name in recipients}

    item_labels = [name for _id, name in items]
    item_map = {name: _id for _id, name in items}

    with st.form("issue_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 2, 1])

        with c1:
            recip_name = st.selectbox("수령자", recip_labels)
        with c2:
            item_name = st.selectbox("품목", item_labels)
        with c3:
            qty = st.number_input("수량", min_value=1, value=1, step=1)

        note = st.text_input("비고(선택)", placeholder="예: 대청소, 특별작업 등")
        submitted = st.form_submit_button("✅ 지급 기록 저장")

        if submitted:
            insert_log(
                ts=datetime.now(),
                recipient_id=recip_map[recip_name],
                item_id=item_map[item_name],
                qty=int(qty),
                note=note.strip() if note else None
            )
            st.success("저장되었습니다.")

    st.divider()

    st.caption("최근 50건")
    df_recent = read_logs()
    if df_recent.empty:
        st.info("아직 기록이 없습니다.")
    else:
        st.dataframe(df_recent.head(50), use_container_width=True)

# =========================================================
# 2) 통계
# =========================================================
elif menu == "📊 통계":
    st.subheader("📊 월별 · 품목별 통계")

    df = read_logs()
    if df.empty:
        st.info("통계를 낼 데이터가 없습니다.")
        st.stop()

    df = df.dropna(subset=["시간"]).copy()
    df["월"] = df["시간"].dt.to_period("M").astype(str)

    month = st.selectbox("월 선택", sorted(df["월"].unique()))
    mdf = df[df["월"] == month].copy()

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### 품목별 총 소모량")
        item_stats = mdf.groupby("품목")["수량"].sum().reset_index().sort_values("수량", ascending=False)
        chart1 = alt.Chart(item_stats).mark_bar().encode(
            x=alt.X("수량:Q", title="총 소모량"),
            y=alt.Y("품목:N", sort="-x", title="품목"),
            tooltip=["품목", "수량"]
        )
        st.altair_chart(chart1, use_container_width=True)
        st.dataframe(item_stats, use_container_width=True)

    with c2:
        st.markdown("### 수령자별 소모량")
        recip_stats = mdf.groupby("수령자")["수량"].sum().reset_index().sort_values("수량", ascending=False)
        chart2 = alt.Chart(recip_stats).mark_bar().encode(
            x=alt.X("수량:Q", title="총 소모량"),
            y=alt.Y("수령자:N", sort="-x", title="수령자"),
            tooltip=["수령자", "수량"]
        )
        st.altair_chart(chart2, use_container_width=True)
        st.dataframe(recip_stats, use_container_width=True)

    st.markdown("### 수령자 × 품목 (누적)")
    pivot = mdf.groupby(["수령자", "품목"])["수량"].sum().reset_index()
    chart3 = alt.Chart(pivot).mark_bar().encode(
        x=alt.X("수령자:N", title="수령자"),
        y=alt.Y("수량:Q", title="수량"),
        color="품목:N",
        tooltip=["수령자", "품목", "수량"]
    )
    st.altair_chart(chart3, use_container_width=True)

# =========================================================
# 3) 조회/다운로드
# =========================================================
elif menu == "📁 내역 조회/다운로드":
    st.subheader("📁 내역 조회 · 다운로드")

    df = read_logs()
    if df.empty:
        st.info("다운로드할 기록이 없습니다.")
        st.stop()

    df = df.dropna(subset=["시간"]).copy()

    with st.expander("필터", expanded=True):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])

        min_d = df["시간"].dt.date.min()
        max_d = df["시간"].dt.date.max()

        with c1:
            start = st.date_input("시작일", value=min_d, min_value=min_d, max_value=max_d)
        with c2:
            end = st.date_input("종료일", value=max_d, min_value=min_d, max_value=max_d)

        recipients_all = run("SELECT id, name FROM recipients ORDER BY name", fetch=True)
        items_all = run("SELECT id, name FROM items ORDER BY name", fetch=True)

        recip_names = ["(전체)"] + [n for _id, n in recipients_all]
        item_names = ["(전체)"] + [n for _id, n in items_all]

        with c3:
            recip_sel = st.selectbox("수령자", recip_names, key="dl_recip_sel")
        with c4:
            item_sel = st.selectbox("품목", item_names, key="dl_item_sel")

    recip_id = None
    item_id = None
    if recip_sel != "(전체)":
        recip_id = next((_id for _id, n in recipients_all if n == recip_sel), None)
    if item_sel != "(전체)":
        item_id = next((_id for _id, n in items_all if n == item_sel), None)

    filtered = read_logs(start=start, end=end, recipient_id=recip_id, item_id=item_id)
    filtered = filtered.dropna(subset=["시간"]).copy()

    st.caption(f"조회 결과: {len(filtered)}건")
    st.dataframe(filtered, use_container_width=True)

    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        csv_bytes = filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ CSV 다운로드",
            data=csv_bytes,
            file_name="소모품_지급내역.csv",
            mime="text/csv",
            key="dl_csv"
        )

    with c2:
        buffer = BytesIO()
        filtered.to_excel(buffer, index=False)
        buffer.seek(0)
        st.download_button(
            "⬇️ Excel 다운로드",
            data=buffer,
            file_name="소모품_지급내역.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_xlsx"
        )

# =========================================================
# 4) 관리자
# =========================================================
elif menu == "⚙️ 관리자":
    st.subheader("⚙️ 관리자")

    pw = st.text_input("관리자 비밀번호", type="password")
    if pw != ADMIN_PASSWORD:
        st.warning("관리자 비밀번호를 입력하세요.")
        st.stop()

    st.success("관리자 인증 완료")

    tab1, tab2, tab3 = st.tabs(["수령자 관리", "품목 관리", "기록 관리(삭제)"])

    # -------------------------
    # 수령자 관리
    # -------------------------
    with tab1:
        st.markdown("### 수령자 관리")
        st.caption("• 비활성화하면 지급 입력 화면에서 선택되지 않습니다. (기록은 보존됨)")

        all_r = get_all_recipients()
        rdf = pd.DataFrame(all_r, columns=["id", "이름", "활성"])
        rdf["활성"] = rdf["활성"].map(lambda x: "활성" if x == 1 else "비활성")
        st.dataframe(rdf, use_container_width=True)

        st.markdown("#### 수령자 추가 (여러 명 가능)")
        new_names = st.text_area("한 줄에 한 명씩 입력", height=120, placeholder="예)\n홍길동\n김철수", key="recip_add_area")
        if st.button("➕ 수령자 추가", key="recip_add_btn"):
            add_recipients(new_names.splitlines())
            st.success("추가 완료. (중복은 자동 무시)")
            st.rerun()

        st.divider()
        st.markdown("#### 수령자 수정/삭제/활성 전환")

        if not all_r:
            st.info("수령자가 없습니다.")
        else:
            options = [(rid, name, active) for rid, name, active in all_r]
            labels = [f"[{rid}] {name} ({'활성' if active == 1 else '비활성'})" for rid, name, active in options]

            sel_label = st.selectbox("대상 선택", labels, key="recip_select")
            sel_idx = labels.index(sel_label)
            sel_id, sel_name, sel_active = options[sel_idx]

            c1, c2 = st.columns([2, 1])
            with c1:
                new_name = st.text_input("이름 수정", value=sel_name, key="recip_new_name")
            with c2:
                st.write("")
                st.write(f"현재 상태: **{'활성' if sel_active == 1 else '비활성'}**")

            b1, b2, b3, b4 = st.columns(4)

            with b1:
                if st.button("✏️ 이름 저장", key="recip_save_name"):
                    try:
                        update_recipient_name(int(sel_id), new_name)
                        st.success("이름 수정 완료")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("같은 이름이 이미 존재합니다. (중복 불가)")
                    except Exception as e:
                        st.error(str(e))

            with b2:
                if sel_active == 1:
                    if st.button("🚫 비활성화", key="recip_deact_btn"):
                        deactivate_recipient(int(sel_id))
                        st.success("비활성화 완료")
                        st.rerun()
                else:
                    if st.button("✅ 활성화", key="recip_act_btn"):
                        activate_recipient(int(sel_id))
                        st.success("활성화 완료")
                        st.rerun()

            with b3:
                if st.button("🗑️ 완전 삭제", key="recip_hard_delete"):
                    try:
                        hard_delete_recipient(int(sel_id))
                        st.success("완전 삭제 완료")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            with b4:
                st.caption("※ 기록이 연결된 수령자는\n완전 삭제가 막힙니다.\n(비활성화 권장)")

    # -------------------------
    # 품목 관리
    # -------------------------
    with tab2:
        st.markdown("### 품목 관리")
        st.caption("• 비활성화하면 지급 입력 화면에서 선택되지 않습니다. (기록은 보존됨)")

        all_i = get_all_items()
        idf = pd.DataFrame(all_i, columns=["id", "품목명", "활성"])
        idf["활성"] = idf["활성"].map(lambda x: "활성" if x == 1 else "비활성")
        st.dataframe(idf, use_container_width=True)

        st.markdown("#### 품목 추가 (여러 개 가능)")
        new_items = st.text_area("한 줄에 한 품목씩 입력", height=120, placeholder="예)\n탈취제\n방향제", key="item_add_area")
        if st.button("➕ 품목 추가", key="item_add_btn"):
            add_items(new_items.splitlines())
            st.success("추가 완료. (중복은 자동 무시)")
            st.rerun()

        st.divider()
        st.markdown("#### 품목 수정/삭제/활성 전환")

        if not all_i:
            st.info("품목이 없습니다.")
        else:
            options = [(iid, name, active) for iid, name, active in all_i]
            labels = [f"[{iid}] {name} ({'활성' if active == 1 else '비활성'})" for iid, name, active in options]

            sel_label = st.selectbox("대상 선택", labels, key="item_select")
            sel_idx = labels.index(sel_label)
            sel_id, sel_name, sel_active = options[sel_idx]

            c1, c2 = st.columns([2, 1])
            with c1:
                new_name = st.text_input("품목명 수정", value=sel_name, key="item_new_name")
            with c2:
                st.write("")
                st.write(f"현재 상태: **{'활성' if sel_active == 1 else '비활성'}**")

            b1, b2, b3, b4 = st.columns(4)

            with b1:
                if st.button("✏️ 품목명 저장", key="item_save_name"):
                    try:
                        update_item_name(int(sel_id), new_name)
                        st.success("품목명 수정 완료")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("같은 품목명이 이미 존재합니다. (중복 불가)")
                    except Exception as e:
                        st.error(str(e))

            with b2:
                if sel_active == 1:
                    if st.button("🚫 비활성화", key="item_deact_btn"):
                        deactivate_item(int(sel_id))
                        st.success("비활성화 완료")
                        st.rerun()
                else:
                    if st.button("✅ 활성화", key="item_act_btn"):
                        activate_item(int(sel_id))
                        st.success("활성화 완료")
                        st.rerun()

            with b3:
                if st.button("🗑️ 완전 삭제", key="item_hard_delete"):
                    try:
                        hard_delete_item(int(sel_id))
                        st.success("완전 삭제 완료")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            with b4:
                st.caption("※ 기록이 연결된 품목은\n완전 삭제가 막힙니다.\n(비활성화 권장)")

    # -------------------------
    # 기록 관리(삭제)
    # -------------------------
    with tab3:
        st.markdown("### 기록 관리(삭제)")
        st.caption("• 삭제는 되돌릴 수 없습니다. (실무에서는 가급적 삭제 대신 비고/정정 기록을 권장)")

        df = read_logs()
        if df.empty:
            st.info("삭제할 기록이 없습니다.")
        else:
            st.dataframe(df.head(200), use_container_width=True)
            del_id = st.number_input("삭제할 기록 id", min_value=1, step=1, key="log_del_id")
            if st.button("🗑️ 선택 기록 삭제", key="log_del_btn"):
                delete_log(int(del_id))
                st.success("삭제 완료")
                st.rerun()
