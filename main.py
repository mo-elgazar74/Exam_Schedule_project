"""
main.py — FastAPI Exam Scheduling System
"""

import re, base64, json
from typing import List, Optional
from datetime import date, timedelta

import httpx
import networkx as nx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import scheduler_core as sc

app = FastAPI(title="Exam Scheduling System")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

PALETTE = sc.PALETTE


# ─── Pages ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/result", response_class=HTMLResponse)
async def result_page(request: Request):
    return templates.TemplateResponse("result.html", {"request": request})


# ─── Helpers ──────────────────────────────────────────────────────

def extract_sheet_id(url: str) -> Optional[str]:
    for pattern in [r"/spreadsheets/d/([a-zA-Z0-9-_]+)", r"id=([a-zA-Z0-9-_]+)"]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


async def fetch_official_holidays(start: date, end: date) -> list[dict]:
    years = list({start.year, end.year})
    holidays = []
    calendarific_key = "6nUFzS1BGfSGJzVySFt5gEwwBzjzkRPr"
    
    async with httpx.AsyncClient(timeout=10) as client:
        for year in years:
            calendarific_success = False
            # 1. Try Calendarific API (Primary)
            try:
                resp = await client.get(
                    f"https://calendarific.com/api/v2/holidays?api_key={calendarific_key}&country=EG&year={year}"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for h in data.get("response", {}).get("holidays", []):
                        if "National holiday" in h.get("type", []):
                            iso_date = h["date"]["iso"][:10]
                            h_date = date.fromisoformat(iso_date)
                            if start <= h_date <= end:
                                holidays.append({
                                    "date": iso_date,
                                    "name": h.get("name", "إجازة رسمية"),
                                })
                    calendarific_success = True
            except Exception:
                pass
                
            # 2. Try Nager.Date API (Fallback)
            if not calendarific_success:
                try:
                    resp = await client.get(
                        f"https://date.nager.at/api/v3/PublicHolidays/{year}/EG"
                    )
                    if resp.status_code == 200:
                        for h in resp.json():
                            h_date = date.fromisoformat(h["date"])
                            if start <= h_date <= end:
                                holidays.append({
                                    "date": h["date"],
                                    "name": h.get("localName") or h.get("name", "إجازة رسمية"),
                                })
                except Exception:
                    pass
                    
    # Deduplicate by date
    unique_holidays = {}
    for h in holidays:
        if h["date"] not in unique_holidays:
            unique_holidays[h["date"]] = h
            
    return sorted(unique_holidays.values(), key=lambda x: x["date"])


# ─── API: Parse Sheet ─────────────────────────────────────────────

@app.post("/api/parse-sheet")
async def parse_sheet(
    sheet_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    content = ""
    if sheet_url and sheet_url.strip():
        sheet_id = extract_sheet_id(sheet_url.strip())
        if not sheet_id:
            raise HTTPException(400, "رابط Google Sheets غير صحيح")
        export_url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        )
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(export_url)
        if resp.status_code == 403:
            raise HTTPException(
                403,
                "الشيت برايفت! ادخل على الشيت → Share → "
                "غيّر لـ 'Anyone with the link can view' ثم جرب تاني.",
            )
        if resp.status_code != 200:
            raise HTTPException(400, f"فشل تحميل الشيت (HTTP {resp.status_code})")
        content = resp.text

    elif file:
        raw = await file.read()
        for enc in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
            try:
                content = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not content:
            raise HTTPException(400, "تعذّر قراءة الملف — تأكد أنه CSV")
    else:
        raise HTTPException(400, "أرسل ملف أو رابط Google Sheets")

    students = sc.load_data_from_content(content)
    if not students:
        raise HTTPException(400, "لم يُعثر على بيانات في الملف — تحقق من تنسيق CSV")

    all_courses = sorted({c for cs in students.values() for c in cs})
    
    # Calculate min days
    G = sc.build_graph(students)
    cmap = sc.greedy_coloring(G)
    min_days = max(cmap.values()) + 1 if cmap else 0

    return {
        "success": True,
        "courses": all_courses,
        "student_count": len(students),
        "course_count": len(all_courses),
        "min_days": min_days,
        "csv_b64": base64.b64encode(content.encode()).decode(),
    }


# ─── API: Holidays ────────────────────────────────────────────────

@app.get("/api/holidays")
async def get_holidays(start_date: str, end_date: str):
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    official = await fetch_official_holidays(start, end)
    return {"official_holidays": official}


# ─── API: Schedule ────────────────────────────────────────────────

class PinnedCourse(BaseModel):
    course: str
    date: str   # YYYY-MM-DD


class ScheduleRequest(BaseModel):
    start_date: str
    end_date: str
    csv_b64: str
    pinned_courses: List[PinnedCourse] = []
    university_holidays: List[str] = []   # YYYY-MM-DD list

def distribute_days(valid_days: List[str], num_days: int, pinned_dates: List[str]) -> List[str]:
    if num_days >= len(valid_days):
        return valid_days
    
    selected = set(pinned_dates)
    if num_days <= len(selected):
        return sorted(list(selected), key=lambda x: valid_days.index(x))
        
    if not selected:
        selected.add(valid_days[0])
        if num_days > 1:
            selected.add(valid_days[-1])
            
    while len(selected) < num_days:
        best_day = None
        max_dist = -1
        for d in valid_days:
            if d not in selected:
                dist = min(abs(valid_days.index(d) - valid_days.index(s)) for s in selected)
                if dist > max_dist:
                    max_dist = dist
                    best_day = d
        if best_day:
            selected.add(best_day)
            
    return sorted(list(selected), key=lambda x: valid_days.index(x))


@app.post("/api/schedule")
async def schedule(data: ScheduleRequest):
    # ── Decode CSV ──────────────────────────────────────────────
    try:
        csv_content = base64.b64decode(data.csv_b64).decode("utf-8")
    except Exception:
        raise HTTPException(400, "بيانات الشيت تالفة — يرجى إعادة الرفع")

    students = sc.load_data_from_content(csv_content)
    if not students:
        raise HTTPException(400, "لا توجد بيانات طلاب")

    G = sc.build_graph(students)

    # ── Date range & holidays ───────────────────────────────────
    start = date.fromisoformat(data.start_date)
    end   = date.fromisoformat(data.end_date)
    if end < start:
        raise HTTPException(400, "تاريخ النهاية يجب أن يكون بعد تاريخ البداية")

    official_list = await fetch_official_holidays(start, end)
    official_set  = {h["date"] for h in official_list}
    uni_set       = set(data.university_holidays)
    all_holidays  = official_set | uni_set

    # Valid exam days (calendar days in period minus holidays and Fridays)
    all_valid_days = []
    current = start
    while current <= end:
        # Python weekday: Monday=0, ..., Friday=4
        if current.weekday() != 4 and current.isoformat() not in all_holidays:
            all_valid_days.append(current.isoformat())
        current += timedelta(days=1)
        
    if not all_valid_days:
        raise HTTPException(400, "لا توجد أي أيام صالحة للامتحانات في هذه الفترة")

    pinned_dates_list = [pc.date for pc in data.pinned_courses]
    
    # ── Two-Pass Graph Coloring to determine exactly how many days we need ──
    # Pass 1: Get base chromatic number without constraints
    cmap_initial = sc.greedy_coloring(G)
    C = max(cmap_initial.values()) + 1 if cmap_initial else 0
    
    if C > len(all_valid_days):
        raise HTTPException(
            400,
            f"الفترة الزمنية غير كافية! الخوارزمية تحتاج {C} أيام "
            f"لكن المتاح {len(all_valid_days)} يوم فقط. قم بتوسيع الفترة."
        )
        
    valid_days = distribute_days(all_valid_days, C, pinned_dates_list)

    # ── Validate & map pinned courses ───────────────────────────
    pre_assigned = {}
    for pc in data.pinned_courses:
        if pc.course not in G.nodes():
            raise HTTPException(400, f"المادة '{pc.course}' غير موجودة في البيانات")
        if pc.date in all_holidays:
            raise HTTPException(400, f"'{pc.course}' مقيدة بيوم إجازة ({pc.date})")
        if pc.date not in all_valid_days:
            raise HTTPException(400, f"'{pc.course}' مقيدة بتاريخ خارج الفترة ({pc.date})")
        pre_assigned[pc.course] = valid_days.index(pc.date)

    # Check pinned-pinned conflicts
    pinned_items = list(pre_assigned.items())
    for i, (c1, s1) in enumerate(pinned_items):
        for c2, s2 in pinned_items[i + 1:]:
            if s1 == s2 and G.has_edge(c1, c2):
                raise HTTPException(
                    400,
                    f"تعارض بين مادتين مقيدتين بنفس اليوم: '{c1}' و '{c2}' ({valid_days[s1]})",
                )

    # Pass 2: Run algorithm with constraints
    color_map = sc.greedy_coloring(G, pre_assigned)
    final_C = max(color_map.values()) + 1 if color_map else 0
    
    # If constraints increased the chromatic number, we must distribute again
    if final_C > C:
        if final_C > len(all_valid_days):
            raise HTTPException(
                400,
                f"بسبب المواد المقيدة، زاد عدد الأيام المطلوبة لـ {final_C} أيام "
                f"وهو أكبر من الأيام المتاحة ({len(all_valid_days)})."
            )
        valid_days = distribute_days(all_valid_days, final_C, pinned_dates_list)
        pre_assigned = {pc.course: valid_days.index(pc.date) for pc in data.pinned_courses}
        color_map = sc.greedy_coloring(G, pre_assigned)
        final_C = max(color_map.values()) + 1 if color_map else 0

    ok, verify_msg = sc.verify(G, color_map)

    # ── Build base dated slots ───────────────────────────────────
    base_slots = sc.build_slots(color_map)
    dated_slots = {}
    for slot_num in sorted(base_slots.keys()):
        dated_slots[valid_days[slot_num]] = sorted(base_slots[slot_num])

    an = sc.analytics(G, students, color_map)

    # ── Generate Multi-Option Schedules ─────────────────────────
    # Always produce exactly 5 options: min_days + 4 others spread to max_possible
    min_days_count = final_C
    max_possible   = len(all_valid_days)
    N_OPTIONS      = 5

    if max_possible <= min_days_count:
        # Only one option possible
        raw_targets = [min_days_count]
    elif max_possible - min_days_count < N_OPTIONS - 1:
        # Range too narrow — use every integer in range
        raw_targets = list(range(min_days_count, max_possible + 1))
    else:
        # Evenly space N_OPTIONS from min to max (always includes both endpoints)
        raw_targets = sorted(set(
            min_days_count + round(i * (max_possible - min_days_count) / (N_OPTIONS - 1))
            for i in range(N_OPTIONS)
        ))

    options = []
    for target in raw_targets:
        opt_slots = sc.split_slots_to_target(base_slots, target)
        actual_target = len(opt_slots)

        # Distribute actual_target days evenly across the valid period
        opt_valid_days = distribute_days(all_valid_days, actual_target, pinned_dates_list)

        opt_dated: dict = {}
        for idx, slot_key in enumerate(sorted(opt_slots.keys())):
            if idx < len(opt_valid_days):
                opt_dated[opt_valid_days[idx]] = sorted(opt_slots[slot_key])

        score = sc.score_option(opt_slots, students, opt_dated)
        options.append({
            "n_days":      actual_target,
            "dated_slots": opt_dated,
            "score":       score,
            "is_best":     False,
        })

    # Mark best option (highest combined score)
    if options:
        best_idx = max(range(len(options)), key=lambda i: options[i]["score"]["combined"])
        options[best_idx]["is_best"] = True
        # Use best option as the default dated_slots
        dated_slots = options[best_idx]["dated_slots"]
        # Update stats to reflect the chosen option
        best_n = options[best_idx]["n_days"]
    else:
        best_n = len(dated_slots)

    # ── Build vis.js graph data ─────────────────────────────────
    pos       = nx.spring_layout(G, seed=42, k=2.5)
    pinned_set = {pc.course for pc in data.pinned_courses}

    vnodes = []
    for n in G.nodes():
        s   = color_map[n]
        col = PALETTE[s % len(PALETTE)]
        x, y = pos[n]
        words = n.split()
        label = " ".join(words[:2]) + ("…" if len(words) > 2 else "")
        exam_date = valid_days[s] if s < len(valid_days) else f"Slot {s}"
        is_pinned = n in pinned_set
        vnodes.append({
            "id": n, "label": label,
            "color": {
                "background": col,
                "border": "#ffd700" if is_pinned else "rgba(255,255,255,0.6)",
                "highlight": {"background": col, "border": "#fff"},
            },
            "font": {"color": "#fff", "size": 12, "face": "Inter,Arial", "bold": True},
            "x": int(x * 520), "y": int(y * 520),
            "title": f"{n}\n📅 {exam_date}\n🔗 Conflicts: {G.degree(n)}"
                     + ("\n📌 Pinned" if is_pinned else ""),
            "widthConstraint": {"minimum": 90, "maximum": 130},
            "borderWidth": 3 if is_pinned else 2,
            "shadow": True,
        })

    vedges = []
    for u, v in G.edges():
        w = G[u][v].get("weight", 1)
        vedges.append({
            "from": u, "to": v, "value": w,
            "title": f"Shared students: {w}",
            "color": {"color": "rgba(100,120,220,0.28)", "highlight": "#7986cb"},
        })

    # ── Slot load keyed by date (default = best option) ─────────
    dated_slot_load = {
        d: len(courses) for d, courses in dated_slots.items()
    }
    dated_slot_students = {
        d: sum(1 for s_courses in students.values() if any(c in courses for c in s_courses))
        for d, courses in dated_slots.items()
    }

    return {
        "success": True,
        "dated_slots": dated_slots,
        "valid_days": valid_days,
        "official_holidays": official_list,
        "university_holidays": data.university_holidays,
        "pinned_courses": [pc.model_dump() for pc in data.pinned_courses],
        "options": options,
        "stats": {
            "courses":    G.number_of_nodes(),
            "students":   len(students),
            "edges":      G.number_of_edges(),
            "exam_days":  best_n,
            "chromatic":  an["chromatic"],
            "density":    an["density"],
        },
        "analytics": {
            "deg_list":       [[n, d] for n, d in an["deg_list"][:15]],
            "edge_data":      [[u, v, w] for u, v, w in an["edge_data"][:12]],
            "heavy_stud":     an.get("heavy_stud", []),
            "top_enrollment": an.get("top_enrollment", [])[:15],
            "slot_students":  dated_slot_students,
            "slot_load":      dated_slot_load,
            "chromatic":      an["chromatic"],
            "density":        an["density"],
        },
        "graph": {"nodes": vnodes, "edges": vedges},
        "students": {name: list(courses) for name, courses in students.items()},
        "verification": {"ok": ok, "message": verify_msg},
        "palette": PALETTE,
    }
