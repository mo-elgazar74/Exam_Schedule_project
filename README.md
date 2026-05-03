# 🎓 Intelligent Exam Scheduling System
### Graph Coloring Algorithm — Algorithms Course Project

---

## 📌 Project Overview

This project is an **Intelligent Exam Scheduling System** that uses the **Graph Coloring Algorithm** to solve a classic scheduling problem: how do we arrange exams for a group of students such that **no student has two exams on the same day**?

The core idea comes from graph theory — if we represent each course as a node, and draw an edge between any two courses shared by at least one student, the problem transforms into a **Graph Coloring Problem**: what is the minimum number of colors (days) needed to color the graph such that no two adjacent nodes share the same color?

---

## 🧠 Algorithm Used

### Graph Coloring — Greedy (Largest Degree First)

**Why Graph Coloring?**
- Exam scheduling is a classic, real-world instance of the Graph Coloring problem.
- Our goal: guarantee that no student has a scheduling conflict in their exams.
- The **chromatic number** of the graph determines the **minimum possible number of exam days**.

**Algorithm Steps:**

```
1. Read student and course data from a CSV file
2. Build the Conflict Graph:
   - Each course  →  Node
   - Any two courses taken by the same student  →  Edge between them
3. Sort nodes in descending order by degree (most conflicted first)
4. Greedy coloring:
   - For each course: assign the smallest number (day) not already
     used by any of its neighbors
5. Verify the schedule: no two adjacent nodes share the same color
6. Map each color (slot number) to an actual calendar date,
   skipping holidays and Fridays
```

**Is Greedy Optimal?**
Not always — but:
- It runs in **polynomial time**, unlike the exact optimal solution which is NP-Hard.
- With the **Largest Degree First** ordering, it produces excellent results in practice.
- It scales well to real university data sizes.

**Complexity:**
- Building the graph: **O(S × C²)** — S = students, C = courses
- Greedy coloring: **O(V + E)** — V = courses, E = conflicts

---

## 🗂️ Required Data Format

### CSV File Format

```
Student Name, Course 1, Course 2, Course 3, ..., Course 8
Ahmed Ali,    Math,     Physics,  CS101,    Chemistry
Sara Mohamed, Math,     English,  History
...
```

- First row: header (skipped automatically)
- Column 1: student name
- Columns 2–9: course names (up to 8 per student)
- Students with fewer than 8 courses are fully supported

### Supported Data Sources
1. ✅ Direct CSV file upload
2. ✅ Google Sheets URL (with "Anyone with the link can view" permission)

---

## ✨ Key Features

### 1. 🔀 Multi-Option Schedule Generation
The system generates **5 different schedule variants**, each with a different number of exam days (ranging from the minimum chromatic number up to the maximum available in the selected date range). This lets the administrator choose the most suitable option.

### 2. 🏆 Automated Scoring System
Each schedule option receives a **score from 0 to 100** based on three criteria:
- **Balance (35%)**: how evenly courses are spread across days
- **Student Comfort (35%)**: average gap (in days) between consecutive exams per student
- **Peak Load (30%)**: inverse of the maximum number of exams in a single day

The highest-scoring option is automatically flagged as **"Best Choice"**.

### 3. 📌 Pinned Courses
Users can fix a specific course to a specific date. The algorithm respects this constraint and solves the rest of the schedule around it.

### 4. 🗓️ Holiday Management
- **Official Egyptian holidays** are fetched automatically via an external API
- **University-specific holidays** can be added manually
- **Fridays** are excluded automatically from exam days

### 5. 📊 Rich Visual Analytics
- **Interactive conflict graph** using vis.js (draggable nodes)
- Multiple charts via Plotly:
  - Heatmap of exams and student footprint per day
  - Conflict degree bar chart
  - Enrollment scatter plot
  - Student comfort indicators

### 6. 📥 CSV Export
Download the final schedule as a ready-to-use CSV file.

---

## 🔬 Additional Technical Details

### How is Verification Done?
After coloring the graph, the system iterates over every edge and checks that both endpoints have different colors:
```python
for u, v in G.edges():
    if color_map[u] == color_map[v]:
        return False, f"Conflict: {u} & {v}"
return True, "No conflicts — schedule is valid ✓"
```

### How Are Slots Split?
When the user wants more exam days than the chromatic number, `split_slots_to_target` is used:
- Picks the slot with the most courses
- Splits it into two halves (safe, because courses in the same slot share no conflicts)
- Repeats until the target number of days is reached

```
Example: 3 days → 5 days
Day 1: [Math, Physics, CS, Bio]  →  Day 1: [Math, Physics]
                                     Day 4: [CS, Bio]
```

### Coloring Order
```
Pinned courses first → then by descending degree
```
This ensures that fixed courses influence their neighbors before any free coloring happens, minimizing cascading conflicts.

---

## 📁 Project File Structure

```
Algorithms_Project/
│
├── main.py                  # FastAPI server — endpoints and API logic
├── scheduler_core.py        # Core algorithm — Graph Coloring and all computations
├── requirements.txt         # Python dependencies
│
├── templates/
│   ├── index.html           # Input & configuration page (Frontend)
│   └── result.html          # Results & analytics page (Frontend)
│
└── static/                  # Static assets (CSS / JS if any)
```

---

## 🤝 Contributors

- Academic project for the **Algorithms** course — Year 3, Semester 2

---

## 📄 License

This project is purely academic, created for educational and research purposes.
