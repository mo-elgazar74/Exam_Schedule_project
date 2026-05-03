# 📂 Code Documentation — Exam Scheduling System
### Detailed explanation of every file, function, and data flow

---

## 🗂️ Project Structure Overview

```
Algorithms_Project/
│
├── main.py              ← FastAPI application — server, routes, and API endpoints
├── scheduler_core.py    ← Core algorithm — Graph Coloring and all computations
├── requirements.txt     ← External Python dependencies
│
└── templates/
    ├── index.html       ← Input & configuration page (Frontend)
    └── result.html      ← Results & analytics page (Frontend)
```

---

## 🚀 How to Run the Project

### Prerequisites
Make sure you have **Python 3.10+** installed.

### Step 1 — Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Start the Development Server
Navigate to the project folder first, then run:
```bash
uvicorn main:app --reload --port 8000
```

> `--reload` makes the server auto-restart whenever you edit a Python file (useful during development).

### Step 3 — Open in Browser
```
http://127.0.0.1:8000
```

### Step 4 — Use the Application
1. On the **home page** (`/`): upload your CSV file or paste a Google Sheets link
2. Set the exam date range (start & end date)
3. Optionally pin specific courses to specific dates
4. Click **"Generate Schedule"**
5. You are redirected to the **results page** (`/result`) showing the schedule, interactive graph, and analytics

### Running in Production (Optional)
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 📄 1. `scheduler_core.py` — Core Algorithm

**Role:** Contains all algorithm logic. Completely independent from the web framework — pure Python.

---

### `PALETTE`
```python
PALETTE = ["#4f46e5", "#0ea5e9", ...]  # 20 colors
```
- A list of 20 hex colors used to visually color graph nodes.
- Each color represents a different exam day.

---

### `load_data_from_content(content: str) → dict`
```
Input:  CSV file contents as a string
Output: dict { student_name: [course1, course2, ...] }
```
**What it does:**
- Reads the CSV row by row using Python's built-in `csv` module.
- Skips the header row.
- Extracts the student name from column 1 and courses from columns 2–9.
- Uses a `set` to deduplicate courses per student.
- Returns a dictionary mapping each student to their list of courses.

---

### `build_graph(students: dict) → nx.Graph`
```
Input:  student → courses dictionary
Output: NetworkX undirected Graph (conflict graph)
```
**What it does:**
- Creates one **node** per unique course.
- For each student, creates an **edge** between every pair of their courses.
- Computes the **weight** of each edge = number of students sharing both courses.
- Edge weight is an indicator of **conflict intensity** between two courses.

**Example:**
```
Ahmed takes {Math, Physics} and Sara takes {Math, Physics}
→ Edge between Math and Physics with weight = 2
```

---

### `greedy_coloring(G: nx.Graph, pre_assigned: dict = None) → dict`
```
Input:  conflict graph + (optional) pinned courses {course: slot_index}
Output: dict { course: slot_number }
```
**How the core algorithm works:**

1. **Pinned courses get priority:** Courses that the user locked to a specific date are colored first.
2. **Sort by degree (descending):** Courses with the most conflicts are processed first.
3. **Greedy assignment:**
   ```python
   for node in nodes_sorted:
       neighbor_colors = {color of each neighbor already colored}
       color = 0
       while color in neighbor_colors:
           color += 1
       color_map[node] = color
   ```
4. Returns a dictionary: each course mapped to its slot number (exam day index).

---

### `verify(G: nx.Graph, color_map: dict) → tuple`
```
Input:  conflict graph + color map
Output: (True/False, message string)
```
**What it does:**
- Iterates over every edge in the graph.
- Checks that both endpoints of every edge have **different** slot numbers.
- Returns `(False, "Conflict: A & B")` if any conflict is found.
- Returns `(True, "No conflicts — schedule is valid ✓")` if the schedule is clean.

---

### `build_slots(color_map: dict) → dict`
```
Input:  dict { course: slot_number }
Output: dict { slot_number: [course1, course2, ...] }
```
**What it does:**
- Inverts the color map: from (course → day) to (day → list of courses).
- Result: day 0 has these courses, day 1 has these, and so on.

---

### `analytics(G, students, color_map) → dict`
```
Input:  graph + students dict + color map
Output: dict with all statistics
```
**Computed and returned values:**

| Key | Description |
|-----|-------------|
| `deg_list` | Courses sorted by number of conflicts (descending) |
| `edge_data` | Strongest edges (most shared students) |
| `heavy_stud` | Students with the highest course load |
| `top_enrollment` | Most-enrolled-in courses |
| `slot_students_count` | Number of students present on each exam day |
| `slot_load` | Number of exams per day |
| `chromatic` | Chromatic number (minimum possible exam days) |
| `density` | Graph density (ratio of actual to possible edges) |

---

### `split_slots_to_target(slots_dict: dict, target: int) → dict`
```
Input:  current slots dict + target number of days
Output: slots redistributed across the target number of days
```
**What it does:**
- When the user wants more exam days than the chromatic number allows:
- Picks the slot with the most courses.
- Splits it into two halves — **safe**, because courses in the same slot share no conflicts.
- Repeats until the target day count is reached.

```
Example: 3 days → 5 days
Day 1: [Math, Physics, CS, Bio]  →  Day 1: [Math, Physics]
                                     Day 4: [CS, Bio]
```

---

### `score_option(slots_dict, students, dated_slots) → dict`
```
Input:  a schedule option + students data + slots mapped to real dates
Output: dict { combined, balance, comfort, max_load, avg_gap_days, days }
```
**How scoring works:**

| Criterion | Weight | Calculation |
|-----------|--------|-------------|
| **Balance** | 35% | Lower Coefficient of Variation in courses-per-day = better balance |
| **Comfort** | 35% | Average gap in days between consecutive exams per student (normalized 0–7 days) |
| **Max Load** | 30% | 1 / peak number of exams in a single day |

**Final score:** weighted sum scaled to **0–100**

---

## 📄 2. `main.py` — FastAPI Server

**Role:** Runs the web server, receives requests from the frontend, and delegates computation to `scheduler_core`.

---

### App Setup
```python
app = FastAPI(title="Exam Scheduling System")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
```
- **FastAPI app**: the main web server
- **StaticFiles**: serves static CSS/JS assets
- **Jinja2Templates**: renders HTML pages

---

### `extract_sheet_id(url: str) → Optional[str]`
```
Input:  Google Sheets URL
Output: the Sheet ID string only
```
Extracts the Sheet ID from any Google Sheets URL format using Regex.

---

### `fetch_official_holidays(start, end) → list[dict]`
```
Input:  start date and end date
Output: list of official Egyptian public holidays in that range
```
**What it does:**
1. **Primary:** tries the **Calendarific API** — fetches Egypt's "National holiday" entries for the year.
2. **Fallback:** if Calendarific fails, tries the **Nager.Date API**.
3. Deduplicates results by date and returns them sorted chronologically.

---

### `GET /` — Home Page
```python
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
```
Serves `index.html` — the data input and configuration page.

---

### `GET /result` — Results Page
```python
@app.get("/result", response_class=HTMLResponse)
async def result_page(request: Request):
    return templates.TemplateResponse("result.html", {"request": request})
```
Serves `result.html` — the schedule display and analytics page.

---

### `POST /api/parse-sheet` — Parse Input Data
```
Input  (Form): sheet_url  OR  file (CSV upload)
Output (JSON): { courses, student_count, course_count, min_days, csv_b64 }
```
**What it does:**
1. If a Google Sheets URL is provided: converts it to an export URL and downloads the CSV.
2. If a file is uploaded: reads it trying multiple encodings (utf-8, cp1256, latin-1).
3. Builds the graph and computes the chromatic number (minimum exam days needed).
4. Returns a data preview + the CSV encoded as Base64 for later use.

---

### `GET /api/holidays` — Fetch Holidays
```
Input  (Query): start_date, end_date
Output (JSON):  { official_holidays: [...] }
```
Returns official public holidays for the given date range.

---

### `distribute_days(valid_days, num_days, pinned_dates) → List[str]`
```
Input:  list of valid calendar days + target count + pinned dates
Output: selected dates evenly spread across the period
```
**What it does:**
- Starts with pinned dates as fixed anchors.
- Adds the first and last available days as additional anchors.
- Iteratively picks the day that is farthest from all already-selected days.
- Goal: distribute exam days as evenly as possible across the date range.

---

### `POST /api/schedule` — Generate Schedule
```
Input  (JSON): { start_date, end_date, csv_b64, pinned_courses, university_holidays }
Output (JSON): { dated_slots, options, stats, analytics, graph, verification, ... }
```

**Processing steps:**

```
1.  Decode CSV from Base64
2.  Build the conflict graph
3.  Compute valid exam days (exclude Fridays + all holidays)
4.  Pass 1: Greedy Coloring without constraints → get chromatic number C
5.  Distribute C days evenly across the valid period
6.  Validate pinned courses (dates in range, not holidays)
7.  Check pinned-pinned conflicts (two pinned courses on the same day with an edge)
8.  Pass 2: Greedy Coloring with pinned constraints
9.  Build dated slots (map each slot index to a calendar date)
10. Generate 5 schedule options using split_slots_to_target
11. Score each option and mark the best one
12. Build vis.js node/edge data for the interactive graph
13. Compute analytics for all charts
14. Return all data to the frontend
```

**Response payload:**

| Key | Contents |
|-----|----------|
| `dated_slots` | Final schedule `{ date: [courses] }` |
| `options` | 5 schedule variants with scores |
| `stats` | Summary numbers (courses, students, days, density) |
| `analytics` | Detailed data for all charts |
| `graph` | vis.js nodes and edges for the interactive graph |
| `verification` | Schedule validity check result |
| `official_holidays` | Auto-detected public holidays |

---

## 📄 3. `templates/index.html` — Input Page

**Role:** The frontend interface for entering data and configuring the scheduling run.

**Components:**
- **Data upload**: CSV file upload or Google Sheets URL input
- **Date range**: exam period start and end date pickers
- **Official holidays**: auto-fetched and displayed visually
- **University holidays**: manually add dates with optional labels
- **Pinned Courses**: select a course and lock it to a specific date
- **Data preview**: summary of parsed data before running
- **Schedule button**: submits all settings and triggers the algorithm

---

## 📄 4. `templates/result.html` — Results Page

**Role:** Displays the final schedule along with all visual analytics.

**Sections:**

| Section | Description |
|---------|-------------|
| **Summary Cards** | Total courses, students, exam days, graph density |
| **Schedule Options Dropdown** | Switch between 5 options (with "Best Choice" badge) |
| **Exam Calendar** | Visual calendar view of the generated schedule |
| **Conflict Graph** | Interactive, draggable graph via vis.js |
| **Analytics Charts** | Multiple Plotly charts (see below) |
| **Verification Badge** | Shows whether the schedule is conflict-free |
| **CSV Download** | Export the schedule as a downloadable CSV |

**Charts included:**
1. **Heatmap** — number of exams and student count per day
2. **Conflict Degree Bar** — most conflicted courses
3. **Enrollment Scatter** — course enrollment sizes
4. **Student Comfort Indicator** — average gap between consecutive exams

---

## 🔗 Data Flow Diagram

```
[User] → index.html → POST /api/parse-sheet
                              ↓
                    load_data_from_content()
                    build_graph()
                    greedy_coloring()  → chromatic number
                              ↓
                    ← Response: { courses, min_days, csv_b64 }

[User] → sets dates & options → POST /api/schedule
                              ↓
                    build_graph()
                    greedy_coloring()  ×2  (with/without pins)
                    split_slots_to_target()  ×5 options
                    score_option()  ×5 options
                    analytics()
                              ↓
                    ← Response: { schedule + options + analytics + graph }
                              ↓
                    [result.html] → renders everything
```

---

## 📦 Libraries Used

| Library | Role |
|---------|------|
| `FastAPI` | Web framework — defines all API endpoints |
| `NetworkX` | Graph construction and analysis (Graph Coloring) |
| `httpx` | Async HTTP client (Google Sheets + Holiday APIs) |
| `Pydantic` | Data validation for API request/response models |
| `Jinja2` | HTML template engine |
| `python-multipart` | Enables file upload support in FastAPI |
| `uvicorn` | ASGI server that runs the FastAPI application |
| `vis.js` *(CDN)* | Interactive, draggable conflict graph in the browser |
| `Plotly` *(CDN)* | All analytical charts and visualizations |
