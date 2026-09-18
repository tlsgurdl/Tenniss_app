import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta 
import json
import gspread
from google.oauth2.service_account import Credentials
import calendar
import re
import holidays 

# ==========================================
# 🎨 0. 극강의 UI/UX CSS 강제 주입
# ==========================================
st.set_page_config(page_title="고촌 테니스클럽 출석부", layout="centered", page_icon="🎾")

st.markdown("""
<style>
    /* 입력창 디자인 고정 */
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
    
    /* 💡 [복구 완료] 체크박스 한줄 배치 시 텍스트 짤림 방지 */
    div[data-testid="stCheckbox"] {
        padding: 5px 2px;
        border-radius: 6px;
        transition: background-color 0.2s;
    }
    div[data-testid="stCheckbox"]:hover {
        background-color: #f1f8e9;
    }
    div[data-testid="stCheckbox"] label span {
        white-space: nowrap !important;
        font-size: 13.5px !important;
        font-weight: 600 !important;
    }
    
    /* Expander 그림자 */
    div[data-testid="stExpander"] {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.08);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# ⚙️ 1. 기본 환경 세팅
# ==========================================
kr_holidays = holidays.KR()

time_slots_mapping = {}
for h in range(13, 23):
    label = f"{h}:00 ~ {h+1}:00"
    if h == 22:
        label += " (심야반)"
    time_slots_mapping[f"{h}:00"] = label

def get_weekend_schedule(d_obj):
    is_weekend = d_obj.weekday() >= 5
    is_hol = d_obj in kr_holidays
    
    if not (is_weekend or is_hol):
        return None
        
    is_sunday_or_hol = (d_obj.weekday() == 6 or is_hol)
    
    schedule = {}
    for h in range(13, 23):
        courts = []
        if is_sunday_or_hol:
            if 13 <= h <= 19: courts.append('6')
        else: 
            if 13 <= h <= 20: courts.append('6')
            
        if is_sunday_or_hol:
            if 13 <= h <= 18: courts.append('7')
        else:
            if 13 <= h <= 19: courts.append('7')
            
        if 15 <= h <= 18: courts.append('8')
            
        schedule[str(h)] = courts
    return schedule

def get_closure_text(val):
    clean_val = val.replace(" ", "")
    if "대회" in clean_val: return "🏆 대회"
    if "우천" in clean_val: return "🌧️ 우천취소"
    if "공사" in clean_val: return "🚧 공사중"
    if "휴관" in clean_val or "휴장" in clean_val or "취소" in clean_val or "block" in clean_val: return "🚫 휴관"
    if val.strip() == "휴": return "🚫 휴관" 
    return None

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
# 📅 2. 스케줄 및 시간 데이터 파싱 (한국 시간 고정)
# ==========================================
KST = timezone(timedelta(hours=9))
today_dt = datetime.now(KST)
today_str = today_dt.strftime('%Y-%m-%d')

today_schedule = {} 
monthly_schedule_dict = {} 

cal_generator = calendar.Calendar(firstweekday=0)
month_dates_list = cal_generator.monthdatescalendar(today_dt.year, today_dt.month)

for week in month_dates_list:
    for day in week:
        if day.month == today_dt.month:
            date_s = day.strftime('%Y-%m-%d')
            is_hol = day in kr_holidays
            is_sun = (day.weekday() == 6)
            is_weekend = (day.weekday() >= 5)
            
            monthly_schedule_dict[date_s] = {
                'is_holiday': is_hol,
                'is_sun': is_sun,
                'show_fixed': (is_weekend or is_hol),
                'show_custom': False,
                'custom_data': None,
                'closure': None
            }

fixed_today = get_weekend_schedule(today_dt)
for h in range(13, 23):
    ui_time = time_slots_mapping[f"{h}:00"]
    if fixed_today and str(h) in fixed_today:
        today_schedule[ui_time] = fixed_today[str(h)]
    else:
        today_schedule[ui_time] = []

if sheet_schedule:
    try:
        data = sheet_schedule.get_all_records()
        for row in data:
            date_val = str(row.get('날짜', '')).strip()
            if not date_val: continue
            
            closure_text = None
            has_extra_courts = False
            day_data = {str(h): [] for h in range(18, 23)}
            
            for h in range(13, 23):
                val = str(row.get(f"{h}:00", "")).strip()
                if val:
                    c_txt = get_closure_text(val)
                    if c_txt:
                        closure_text = c_txt
                        break
            
            if not closure_text:
                for h in range(18, 23):
                    val = str(row.get(f"{h}:00", "")).strip()
                    courts = list(re.sub(r'\D', '', val))
                    if '7' in courts: 
                        day_data[str(h)].append('7')
                        has_extra_courts = True
                    if '8' in courts: 
                        day_data[str(h)].append('8')
                        has_extra_courts = True
                        
            if date_val not in monthly_schedule_dict:
                monthly_schedule_dict[date_val] = {
                    'is_holiday': False, 'is_sun': False, 'show_fixed': False, 'show_custom': False, 'custom_data': None, 'closure': None
                }
                
            if closure_text:
                monthly_schedule_dict[date_val]['closure'] = closure_text
                monthly_schedule_dict[date_val]['show_fixed'] = False 
                monthly_schedule_dict[date_val]['show_custom'] = False
            elif has_extra_courts:
                monthly_schedule_dict[date_val]['show_custom'] = True
                monthly_schedule_dict[date_val]['custom_data'] = day_data
                monthly_schedule_dict[date_val]['show_fixed'] = False 

            if date_val == today_str:
                for h in range(13, 23):
                    col_name = f"{h}:00"
                    if col_name in row: 
                        val = str(row.get(col_name, "")).strip()
                        ui_time = time_slots_mapping[col_name]
                        if val:
                            if get_closure_text(val):
                                today_schedule[ui_time] = [] 
                            else:
                                today_schedule[ui_time] = list(re.sub(r'\D', '', val))

    except Exception as e:
        st.warning("⚠️ 스케줄 데이터를 읽는 중 문제가 발생했습니다.")

available_time_slots = [t for t, courts in today_schedule.items() if len(courts) > 0]

# ==========================================
# 📝 3. 데이터 읽기/쓰기 및 세션 상태 제어
# ==========================================
if "clear_input" not in st.session_state:
    st.session_state.clear_input = False

if st.session_state.clear_input:
    # 성공 후 입력창 초기화 로직
    if "pill_member" in st.session_state:
        st.session_state.pill_member = None
    st.session_state.clear_input = False

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

@st.cache_data(ttl=600)
def get_all_members():
    if not sheet: return []
    try:
        all_values = sheet.get_all_values()
        if len(all_values) <= 1: return []
        header = all_values[0]
        if "이름" not in header: return []
        name_idx = header.index("이름")
        
        names = [row[name_idx].strip() for row in all_values[1:] if len(row) > name_idx and row[name_idx].strip()]
        return sorted(list(set(names)))
    except:
        return []

def add_attendance(name, times):
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    rows_to_insert = [[name, t, now] for t in times]
    if sheet:
        sheet.append_rows(rows_to_insert)

def cancel_attendance(name):
    if not sheet: return False
    try:
        all_values = sheet.get_all_values()
        rows_to_delete = []
        search_name = name.strip()
        
        for i, row in enumerate(all_values):
            if len(row) >= 3 and str(row[0]).strip() == search_name and str(row[2]).startswith(today_str):
                rows_to_delete.append(i + 1)
        
        if rows_to_delete:
            for r in sorted(rows_to_delete, reverse=True):
                sheet.delete_rows(r)
            return True
        return False
    except Exception as e:
        st.error(f"취소 중 오류 발생: {e}")
        return False

# ==========================================
# 🖥️ 4. UI 렌더링
# ==========================================
st.title("🎾 고촌클럽 출석부")
tab1, tab2 = st.tabs(["🎾 오늘의 출석부", "📅 월간 예약 달력"])

with tab1:
    st.markdown(f"**📅 오늘 날짜: {today_str}**")
    current_db = fetch_data()

    with st.expander("🙋‍♂️ [회원용] 3초 출석 체크 / 취소", expanded=True):
        if not available_time_slots:
            st.error("오늘은 예약된 코트 일정이 없습니다! 푹 쉬세요 🍺")
        else:
            st.markdown("**1️⃣ 이름 입력** (아래 태그를 누르거나 직접 입력하세요)")
            members = get_all_members()
            pill_val = None
            
            if members:
                try:
                    # 모바일에서도 예쁘게 줄바꿈되는 태그 기능
                    pill_val = st.pills("기존 회원", options=members, key="pill_member", label_visibility="collapsed")
                except AttributeError:
                    sel = st.multiselect("기존 회원", options=members, placeholder="👇 기존 회원 선택 (검색 가능)", max_selections=1, label_visibility="collapsed")
                    pill_val = sel[0] if sel else None

            user_name = st.text_input("닉네임(이름) 입력", value=pill_val if pill_val else "", placeholder="예: 홍길동", label_visibility="collapsed")
            
            st.markdown("---")
            
            # 💡 [복구 완료] 시간 체크박스와 버튼을 '단일 가로줄(Row)'로 완벽하게 묶음
            st.markdown("**2️⃣ 참석 시간 선택** (선택 후 우측 등록/취소 클릭)")
            
            num_slots = len(available_time_slots)
            ratios = [1.3] * num_slots + [1.0, 1.0] 
            main_cols = st.columns(ratios)
            
            selected_times = []
            for idx, time_slot in enumerate(available_time_slots):
                with main_cols[idx]:
                    start_hr = time_slot.split(":")[0]
                    end_hr = time_slot.split(" ~ ")[1].split(":")[0]
                    short_label = f"{start_hr}~{end_hr}시"
                    
                    if st.checkbox(short_label):
                        selected_times.append(time_slot)
                        
            with main_cols[-2]:
                if st.button("🚀 등록", use_container_width=True, type="primary"):
                    if not user_name.strip():
                        st.warning("⚠️ 이름을 입력해 주세요!")
                    elif not selected_times:
                        st.warning("⚠️ 시간을 선택해 주세요!")
                    else:
                        if not current_db.empty and user_name in current_db['이름'].values:
                            st.error(f"🚨 '{user_name}'님은 이미 등록하셨습니다!")
                        else:
                            with st.spinner("기록 중..."):
                                add_attendance(user_name, selected_times)
                                get_all_members.clear() 
                                st.session_state.clear_input = True 
                                st.success(f"🎉 {user_name}님 등록 완료!")
                                st.rerun()
                                
            with main_cols[-1]:
                if st.button("🗑️ 취소", use_container_width=True):
                    if not user_name.strip():
                        st.warning("⚠️ 이름을 입력해 주세요!")
                    else:
                        if current_db.empty or user_name.strip() not in current_db['이름'].str.strip().values:
                            st.warning(f"🚨 출석 내역이 없습니다.")
                        else:
                            with st.spinner("삭제 중..."):
                                is_deleted = cancel_attendance(user_name)
                                if is_deleted:
                                    st.session_state.clear_input = True 
                                    st.success(f"🗑️ 취소 완료!")
                                    st.rerun()
                                else:
                                    st.error("취소에 실패했습니다.")

    st.divider()

    # --- [현황판] ---
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

            courts_html = ""
            for court_num in active_courts:
                court_div = (
                    f"<div style='width: 50px; height: 75px; background-color: {bg_color}; border: 2px solid white; border-radius: 6px; position: relative; box-shadow: 2px 2px 5px rgba(0,0,0,0.25); flex-shrink: 0;'>"
                    f"<div style='position: absolute; top: 0; bottom: 0; left: 15%; border-left: 1px solid rgba(255,255,255,0.5);'></div>"
                    f"<div style='position: absolute; top: 0; bottom: 0; right: 15%; border-right: 1px solid rgba(255,255,255,0.5);'></div>"
                    f"<div style='position: absolute; top: 50%; left: 0; right: 0; border-top: 2px dashed rgba(255,255,255,0.9); transform: translateY(-50%);'></div>"
                    f"<div style='position: absolute; top: 22%; left: 15%; right: 15%; border-top: 1px solid rgba(255,255,255,0.6);'></div>"
                    f"<div style='position: absolute; bottom: 22%; left: 15%; right: 15%; border-top: 1px solid rgba(255,255,255,0.6);'></div>"
                    f"<div style='position: absolute; top: 22%; bottom: 22%; left: 50%; border-left: 1px solid rgba(255,255,255,0.6); transform: translateX(-50%);'></div>"
                    f"<div style='position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; z-index: 10;'>"
                    f"<span style='background-color: rgba(255,255,255,0.95); color: #222; padding: 2px 5px; border-radius: 10px; font-weight: 900; font-size: 12px; box-shadow: 1px 2px 4px rgba(0,0,0,0.3); border: 1px solid #ddd;'>{court_num}번</span>"
                    f"</div></div>"
                )
                courts_html += court_div

            final_html = (
                f"<div style='background-color: #ffffff; padding: 15px; border-radius: 12px; margin-bottom: 15px; border: 1px solid #eee; display: flex; align-items: center; justify-content: flex-start; overflow-x: auto; box-shadow: 0 2px 10px rgba(0,0,0,0.03); gap: 15px;'>"
                f"<div style='min-width: max-content;'>"
                f"<h4 style='margin: 0; color: #333; font-size: 17px;'>{time_slot}</h4>"
                f"<p style='margin: 4px 0 0 0; font-size: 13px; color: #666;'>"
                f"현재 <strong>{people}명</strong><br>"
                f"<span style='font-weight: 800; color: {status_font_color};'>상태: {status_text}</span>"
                f"</p></div>"
                f"<div style='display: flex; gap: 8px; flex-wrap: nowrap;'>{courts_html}</div>"
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
# 🗓️ 5. 두 번째 탭: 월간 예약 달력 
# ==========================================
with tab2:
    st.subheader(f"📅 {today_dt.year}년 {today_dt.month}월 추가 코트 현황")
    
    calendar_html = """
    <style>
        .cal-table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 10px; }
        .cal-th { background-color: #f8f9fa; padding: 8px 0; text-align: center; border: 1px solid #ddd; font-size: 13px; color: #333; }
        .cal-td { border: 1px solid #ddd; height: 125px; vertical-align: top; padding: 4px; background-color: #fff; transition: background 0.2s; }
        .cal-date { font-weight: bold; font-size: 13px; color: #333; margin-bottom: 2px; display: block; text-align: left; padding-left: 2px;}
        .cal-other-month { color: #ccc; background-color: #fafafa; }
        .cal-today { background-color: #e8f5e9; border: 2px solid #4CAF50; }
        
        .mini-table { width: 100%; border-collapse: collapse; text-align: center; margin-top: 3px; table-layout: fixed;}
        .mini-th { font-size: 9px; border: 1px solid #ccc; background-color: #f0f0f0; padding: 0; color: #555; white-space: nowrap;}
        .mini-td { font-size: 9px; border: 1px solid #ccc; padding: 0; height: 11px; white-space: nowrap; word-break: keep-all; letter-spacing: -0.5px;}
        .cell-booked { background-color: #4CAF50; }
        .cell-empty { background-color: #fafafa; }
        
        .closure-badge { display: block; background-color: #ffebee; color: #c62828; font-size: 11px; padding: 5px 3px; border-radius: 4px; font-weight: bold; text-align: center; margin-top: 20px;}
    </style>
    <table class="cal-table">
        <tr>
            <th class="cal-th">월</th><th class="cal-th">화</th><th class="cal-th">수</th>
            <th class="cal-th">목</th><th class="cal-th">금</th><th class="cal-th" style="color:blue;">토</th><th class="cal-th" style="color:red;">일</th>
        </tr>
    """
    
    for week in month_dates_list:
        calendar_html += "<tr>"
        for day in week:
            date_str = day.strftime('%Y-%m-%d')
            day_num = day.day
            
            td_class = "cal-td"
            if day.month != today_dt.month:
                td_class += " cal-other-month"
            if date_str == today_str:
                td_class += " cal-today"
                
            date_display_html = f"<span class='cal-date'>{day_num}"
            content_html = ""
            
            if date_str in monthly_schedule_dict:
                info = monthly_schedule_dict[date_str]
                
                if info['is_holiday']:
                    date_display_html += "<span style='color: #c62828; font-size: 10px; font-weight: 800; margin-left: 4px;'>[연휴]</span>"
                date_display_html += "</span>" 
                
                if info['closure']:
                    content_html = f"<span class='closure-badge'>{info['closure']}</span>"
                
                elif info['show_custom']: 
                    content_html = "<table class='mini-table'><tr><th class='mini-th' style='width:36%;'>시</th><th class='mini-th' style='width:32%;'>7</th><th class='mini-th' style='width:32%;'>8</th></tr>"
                    for hr in ['18', '19', '20', '21', '22']: 
                        cls_7 = "cell-booked" if '7' in info['custom_data'][hr] else "cell-empty"
                        cls_8 = "cell-booked" if '8' in info['custom_data'][hr] else "cell-empty"
                        content_html += f"<tr><td class='mini-td' style='background-color:#f9f9f9; color:#666;'>{hr}</td><td class='mini-td {cls_7}'></td><td class='mini-td {cls_8}'></td></tr>"
                    content_html += "</table>"
                    
                elif info['show_fixed']:
                    badge_label = "[공휴일 고정대관]" if info['is_holiday'] else ("[일요일 고정대관]" if info['is_sun'] else "[토요일 고정대관]")
                    badge_color = "#ffebee" if (info['is_holiday'] or info['is_sun']) else "#e3f2fd"
                    
                    if info['is_holiday'] or info['is_sun']:
                        summary_text = "6번: 13-20시<br>7번: 13-19시<br>8번: 15-19시"
                    else:
                        summary_text = "6번: 13-21시<br>7번: 13-20시<br>8번: 15-19시"
                        
                    content_html = f"""
                    <div style='background-color:{badge_color}; padding:4px; border-radius:4px; margin-top:4px;'>
                        <div style='font-size:9.5px; font-weight:800; text-align:center; margin-bottom:2px;'>{badge_label}</div>
                        <div style='font-size:10px; color:#555; text-align:center; line-height:1.2; letter-spacing:-0.5px;'>{summary_text}</div>
                    </div>
                    """
            else:
                date_display_html += "</span>"
            
            calendar_html += f"<td class='{td_class}'>{date_display_html}{content_html}</td>"
        calendar_html += "</tr>"
        
    calendar_html += "</table>"
    
    st.markdown(calendar_html, unsafe_allow_html=True)
    st.caption("💡 주말/공휴일은 고정 스케줄이 반영되며, 시트에 '휴관', '대회' 등의 정확한 키워드가 있으면 휴장 처리됩니다.")
