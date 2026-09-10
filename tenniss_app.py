import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
import calendar
import re # 💡 숫자를 하나씩 쪼개기 위한 라이브러리

# ==========================================
# 🎨 0. 극강의 UI/UX CSS 강제 주입
# ==========================================
st.set_page_config(page_title="고촌 테니스클럽 출석부", layout="centered", page_icon="🎾")

st.markdown("""
<style>
    /* 1. 텍스트 입력창 테두리 초강력 고정 (절대 안 보일 수 없게 검정색 2px 고정) */
    div[data-testid="stTextInput"] div[data-baseweb="input"] {
        border: 2px solid #000000 !important;
        border-radius: 8px !important;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.15) !important;
        background-color: #ffffff !important;
    }
    div[data-testid="stTextInput"] input {
        color: #000000 !important;
        font-weight: bold !important;
    }
    div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
        border: 2.5px solid #4CAF50 !important;
        box-shadow: 2px 2px 12px rgba(76, 175, 80, 0.4) !important;
    }
    
    /* 체크박스 디자인 */
    div[data-testid="stCheckbox"] {
        padding: 5px 10px;
        border-radius: 6px;
        transition: background-color 0.2s;
    }
    div[data-testid="stCheckbox"]:hover {
        background-color: #f1f8e9;
    }

    /* Expander 그림자 효과 */
    div[data-testid="stExpander"] {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.08);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 1. 기본 환경 세팅 및 구글 시트 연동
# ==========================================
time_slots_mapping = {
    "18:00": "18:00 ~ 19:00",
    "19:00": "19:00 ~ 20:00",
    "20:00": "20:00 ~ 21:00",
    "21:00": "21:00 ~ 22:00"
}

@st.cache_resource(ttl=600)
def init_connection():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        secret_raw = st.secrets["gcp_service_account"]
        key_info = json.loads(secret_raw) if isinstance(secret_raw, str) else dict(secret_raw)
        credentials = Credentials.from_service_account_info(key_info, scopes=scope)
        client = gspread.authorize(credentials)
        
        doc = client.open("고촌테니스_출석부")
        sheet_db = doc.get_worksheet(0)
        try:
            sheet_schedule = doc.worksheet("스케줄")
        except:
            sheet_schedule = None
        return sheet_db, sheet_schedule
    except Exception as e:
        st.error(f"⚠️ 연동 실패: {e}")
        return None, None

sheet, sheet_schedule = init_connection()

# ==========================================
# 📅 2. 스케줄 데이터 파싱 ("67", "678" 분리 로직 추가)
# ==========================================
today_dt = datetime.today()
today_str = today_dt.strftime('%Y-%m-%d')

today_schedule = {} 
monthly_schedule_dict = {} 

if sheet_schedule:
    try:
        data = sheet_schedule.get_all_records()
        for row in data:
            date_val = str(row.get('날짜', '')).strip()
            if not date_val: continue
            
            # --- 1. 오늘 날짜 코트 파싱 (출석부용) ---
            if date_val == today_str:
                for col_time, ui_time in time_slots_mapping.items():
                    val = str(row.get(col_time, "")).strip()
                    if val and "휴" not in val and "block" not in val:
                        # 💡 핵심: "67" -> 숫자만 추출 후 리스트로 분리 -> ['6', '7']
                        digits = re.sub(r'\D', '', val)
                        extracted_courts = list(digits) 
                        today_schedule[ui_time] = extracted_courts
                    else:
                        today_schedule[ui_time] = []
            
            # --- 2. 월간 달력용 미니 표 데이터 파싱 ---
            is_holiday = False
            has_extra_courts = False
            day_data = {'18': [], '19': [], '20': [], '21': []}
            
            for col_time in ['18:00', '19:00', '20:00', '21:00']:
                val = str(row.get(col_time, "")).strip()
                hour = col_time.split(':')[0] # '18', '19' 등
                
                if "휴" in val or "추석" in val:
                    is_holiday = True
                elif val and "block" not in val:
                    digits = re.sub(r'\D', '', val)
                    courts = list(digits)
                    
                    # 7번이나 8번이 있으면 시간대별로 기록
                    if '7' in courts: 
                        day_data[hour].append('7')
                        has_extra_courts = True
                    if '8' in courts: 
                        day_data[hour].append('8')
                        has_extra_courts = True
            
            if is_holiday:
                monthly_schedule_dict[date_val] = "holiday"
            elif has_extra_courts:
                monthly_schedule_dict[date_val] = day_data

    except Exception as e:
        st.warning("⚠️ 스케줄 데이터를 읽는 중 문제가 발생했습니다.")

available_time_slots = [t for t, courts in today_schedule.items() if len(courts) > 0]

# ==========================================
# 📝 3. 출석 데이터 읽기/쓰기
# ==========================================
def fetch_data():
    if sheet:
        try:
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            if not df.empty and '등록일시' in df.columns:
                df = df[df['등록일시'].str.startswith(today_str)]
            return df
        except:
            pass
    return pd.DataFrame(columns=["이름", "참석시간", "등록일시"])

def add_attendance(name, times):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_insert = [[name, t, now] for t in times]
    if sheet:
        sheet.append_rows(rows_to_insert)

# ==========================================
# 🖥️ 4. UI 렌더링: 두 개의 탭 분리
# ==========================================
st.title("🎾 고촌 테니스클럽")
tab1, tab2 = st.tabs(["🎾 오늘의 출석부", "📅 월간 예약 달력"])

with tab1:
    st.markdown(f"**📅 오늘 날짜: {today_str}**")
    current_db = fetch_data()

    # --- [회원용] 출석 체크 창 ---
    with st.expander("🙋‍♂️ [회원용] 3초 출석 체크하기", expanded=True):
        if not available_time_slots:
            st.error("오늘은 예약된 코트 일정이 없습니다! 푹 쉬세요 🍺")
        else:
            col1, col2 = st.columns([1, 2])
            with col1:
                user_name = st.text_input("닉네임(이름) 입력", placeholder="예: 김보람")
            
            with col2:
                st.markdown("참석 시간 선택")
                selected_times = []
                for time_slot in available_time_slots:
                    if st.checkbox(time_slot):
                        selected_times.append(time_slot)
                        
            if st.button("🚀 출석 등록 완료", use_container_width=True):
                if not user_name.strip():
                    st.warning("⚠️ 닉네임을 입력해 주세요!")
                elif not selected_times:
                    st.warning("⚠️ 시간을 선택해 주세요!")
                else:
                    if not current_db.empty and user_name in current_db['이름'].values:
                        st.error(f"🚨 '{user_name}'님은 이미 등록하셨습니다!")
                    else:
                        with st.spinner("기록 중입니다..."):
                            add_attendance(user_name, selected_times)
                            st.success(f"🎉 {user_name}님 등록 완료!")
                            st.rerun()

    st.divider()

    # --- [현황판] 코트 시각화 (각 코트별 독립된 이미지 나란히 표출) ---
    st.subheader("🚥 실시간 코트 현황판")
    if not available_time_slots:
        st.warning("⚠️ 오늘 예약된 코트가 없습니다.")
    else:
        if not current_db.empty and '참석시간' in current_db.columns:
            attendance_counts = current_db['참석시간'].value_counts().to_dict()
        else:
            attendance_counts = {}

        for time_slot, active_courts in today_schedule.items():
            if not active_courts: 
                continue
                
            num_courts = len(active_courts)
            people = attendance_counts.get(time_slot, 0)
            density = people / num_courts if num_courts > 0 else 0
            
            if density < 4.5:
                status_text, bg_color = "쾌적", "#4CAF50"
            elif density <= 6.5:
                status_text, bg_color = "적정", "#FFC107"
            else:
                status_text, bg_color = "포화", "#F44336"

            status_font_color = bg_color if bg_color != "#FFC107" else "#d4a100"

            # 💡 수정됨: 분리된 번호(예: '6', '7')를 이용해 코트를 옆으로(flex) 나란히 그립니다.
            courts_html = ""
            for court_num in active_courts:
                court_div = (
                    f"<div style='width: 55px; height: 85px; background-color: {bg_color}; border: 2px solid white; border-radius: 6px; position: relative; box-shadow: 2px 2px 5px rgba(0,0,0,0.25); flex-shrink: 0;'>"
                    f"<div style='position: absolute; top: 0; bottom: 0; left: 15%; border-left: 1px solid rgba(255,255,255,0.5);'></div>"
                    f"<div style='position: absolute; top: 0; bottom: 0; right: 15%; border-right: 1px solid rgba(255,255,255,0.5);'></div>"
                    f"<div style='position: absolute; top: 50%; left: 0; right: 0; border-top: 2px dashed rgba(255,255,255,0.9); transform: translateY(-50%);'></div>"
                    f"<div style='position: absolute; top: 22%; left: 15%; right: 15%; border-top: 1px solid rgba(255,255,255,0.6);'></div>"
                    f"<div style='position: absolute; bottom: 22%; left: 15%; right: 15%; border-top: 1px solid rgba(255,255,255,0.6);'></div>"
                    f"<div style='position: absolute; top: 22%; bottom: 22%; left: 50%; border-left: 1px solid rgba(255,255,255,0.6); transform: translateX(-50%);'></div>"
                    f"<div style='position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; z-index: 10;'>"
                    f"<span style='background-color: rgba(255,255,255,0.95); color: #222; padding: 3px 6px; border-radius: 12px; font-weight: 900; font-size: 13px; box-shadow: 1px 2px 4px rgba(0,0,0,0.3); border: 1px solid #ddd;'>{court_num}번</span>"
                    f"</div></div>"
                )
                courts_html += court_div

            final_html = (
                f"<div style='background-color: #ffffff; padding: 15px; border-radius: 12px; margin-bottom: 15px; border: 1px solid #eee; display: flex; align-items: center; justify-content: space-between; overflow-x: auto; box-shadow: 0 2px 10px rgba(0,0,0,0.03);'>"
                f"<div style='flex: 1; min-width: 130px;'>"
                f"<h4 style='margin: 0; color: #333; font-size: 17px;'>{time_slot}</h4>"
                f"<p style='margin: 5px 0 0 0; font-size: 14px; color: #666;'>"
                f"현재 <strong>{people}명</strong> (코트당 {density:.1f}명) <br>"
                f"<span style='font-weight: 800; color: {status_font_color};'>상태: {status_text}</span>"
                f"</p></div>"
                f"<div style='display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end;'>{courts_html}</div>"
                f"</div>"
            )
            st.markdown(final_html, unsafe_allow_html=True)

    with st.expander("📋 시간대별 상세 참석자 명단"):
        if current_db.empty or '참석시간' not in current_db.columns:
            st.write("아직 등록된 회원이 없습니다.")
        else:
            summary_df = current_db.groupby('참석시간')['이름'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
            st.table(summary_df)

# ==========================================
# 🗓️ 5. 두 번째 탭: 월간 예약 달력 (미니 히트맵 표 적용)
# ==========================================
with tab2:
    st.subheader(f"📅 {today_dt.year}년 {today_dt.month}월 추가 코트 현황")
    
    cal = calendar.Calendar(firstweekday=0)
    month_dates = cal.monthdatescalendar(today_dt.year, today_dt.month)
    
    calendar_html = """
    <style>
        .cal-table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 10px; }
        .cal-th { background-color: #f8f9fa; padding: 8px 0; text-align: center; border: 1px solid #ddd; font-size: 13px; color: #333; }
        .cal-td { border: 1px solid #ddd; height: 110px; vertical-align: top; padding: 4px; background-color: #fff; transition: background 0.2s; }
        .cal-td:hover { background-color: #f1f8e9; }
        .cal-date { font-weight: bold; font-size: 13px; color: #333; margin-bottom: 2px; display: block; text-align: left; padding-left: 2px;}
        .cal-other-month { color: #ccc; background-color: #fafafa; }
        .cal-today { background-color: #e8f5e9; border: 2px solid #4CAF50; }
        
        /* 미니 표 스타일 */
        .mini-table { width: 100%; border-collapse: collapse; text-align: center; margin-top: 3px; table-layout: fixed;}
        .mini-th { font-size: 9px; border: 1px solid #ccc; background-color: #f0f0f0; padding: 1px 0; color: #555;}
        .mini-td { font-size: 9px; border: 1px solid #ccc; padding: 1px 0; height: 14px;}
        .cell-booked { background-color: #4CAF50; } /* 예약된 칸은 초록색 */
        .cell-empty { background-color: #fafafa; }  /* 빈 칸은 연회색 */
        
        .holiday-badge { display: block; background-color: #ffebee; color: #c62828; font-size: 11px; padding: 3px; border-radius: 4px; font-weight: bold; text-align: center; margin-top: 15px;}
    </style>
    <table class="cal-table">
        <tr>
            <th class="cal-th">월</th><th class="cal-th">화</th><th class="cal-th">수</th>
            <th class="cal-th">목</th><th class="cal-th">금</th><th class="cal-th" style="color:blue;">토</th><th class="cal-th" style="color:red;">일</th>
        </tr>
    """
    
    for week in month_dates:
        calendar_html += "<tr>"
        for day in week:
            date_str = day.strftime('%Y-%m-%d')
            day_num = day.day
            
            td_class = "cal-td"
            if day.month != today_dt.month:
                td_class += " cal-other-month"
            if date_str == today_str:
                td_class += " cal-today"
                
            content_html = ""
            
            # 💡 [핵심] 7번, 8번 예약이 있는 날짜에만 미니 표 렌더링
            if date_str in monthly_schedule_dict:
                data = monthly_schedule_dict[date_str]
                if data == "holiday":
                    content_html = "<span class='holiday-badge'>🌕 연휴/휴장</span>"
                else:
                    # 미니 표 생성 시작
                    content_html = """
                    <table class='mini-table'>
                        <tr>
                            <th class='mini-th' style='width:34%;'>시</th>
                            <th class='mini-th' style='width:33%;'>7번</th>
                            <th class='mini-th' style='width:33%;'>8번</th>
                        </tr>
                    """
                    # 18시, 19시, 20시, 21시 순회하며 행 추가
                    for hr in ['18', '19', '20', '21']:
                        # 7번 코트 색칠 여부
                        cls_7 = "cell-booked" if '7' in data[hr] else "cell-empty"
                        # 8번 코트 색칠 여부
                        cls_8 = "cell-booked" if '8' in data[hr] else "cell-empty"
                        
                        content_html += f"""
                        <tr>
                            <td class='mini-td' style='background-color:#f9f9f9; color:#666;'>{hr}</td>
                            <td class='mini-td {cls_7}'></td>
                            <td class='mini-td {cls_8}'></td>
                        </tr>
                        """
                    content_html += "</table>"
                
            calendar_html += f"<td class='{td_class}'><span class='cal-date'>{day_num}</span>{content_html}</td>"
        calendar_html += "</tr>"
        
    calendar_html += "</table>"
    
    st.markdown(calendar_html, unsafe_allow_html=True)
    st.caption("💡 6번 코트는 상시 고정이며, 달력에는 추가로 예약된 **7번, 8번 코트** 현황만 🟢초록색으로 표시됩니다.")
