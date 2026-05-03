"""
scheduler_core.py — Algorithm logic for Exam Scheduling System
Greedy Graph Coloring (Largest-Degree-First) with optional pinned constraints
"""

import io, csv
import networkx as nx
from collections import defaultdict

PALETTE = [
    "#4f46e5", "#0ea5e9", "#059669", "#d97706", "#dc2626",
    "#7c3aed", "#2563eb", "#0d9488", "#ca8a04", "#e11d48",
    "#9333ea", "#0284c7", "#16a34a", "#ea580c", "#c026d3",
    "#4338ca", "#0369a1", "#15803d", "#b45309", "#be123c"
]

# ── Load data from CSV string ─────────────────────────────────────
def load_data_from_content(content: str) -> dict:
    students = {}
    reader = csv.reader(io.StringIO(content))
    next(reader, None)  # skip header
    for row in reader:
        if not row:
            continue
        name = row[0].strip()
        if not name:
            continue
        courses = list({c.strip() for c in row[1:10] if c.strip()})
        if courses:
            students[name] = courses
    return students

# ── Build conflict graph ──────────────────────────────────────────
def build_graph(students: dict) -> nx.Graph:
    G = nx.Graph()
    all_courses = set()
    for c in students.values():
        all_courses.update(c)
    G.add_nodes_from(all_courses)

    ew = defaultdict(int)
    for courses in students.values():
        cl = list(courses)
        for i in range(len(cl)):
            for j in range(i + 1, len(cl)):
                k = tuple(sorted([cl[i], cl[j]]))
                ew[k] += 1
                if not G.has_edge(cl[i], cl[j]):
                    G.add_edge(cl[i], cl[j])

    nx.set_edge_attributes(
        G,
        {(u, v): ew[tuple(sorted([u, v]))] for u, v in G.edges()},
        "weight"
    )
    return G

# ── Greedy coloring with optional pre-assigned slots ─────────────
def greedy_coloring(G: nx.Graph, pre_assigned: dict = None) -> dict:
    """
    pre_assigned: {course_name: slot_index}  (pinned courses)
    """
    if pre_assigned is None:
        pre_assigned = {}

    color_map = dict(pre_assigned)

    # Sort: pinned first (so their neighbors see them), then by degree desc
    def sort_key(n):
        return (0 if n in pre_assigned else 1, -G.degree(n))

    nodes_sorted = sorted(G.nodes(), key=sort_key)

    for node in nodes_sorted:
        if node in color_map:
            continue
        neighbor_colors = {color_map[nb] for nb in G.neighbors(node) if nb in color_map}
        color = 0
        while color in neighbor_colors:
            color += 1
        color_map[node] = color

    return color_map

# ── Verify no adjacent nodes share a color ───────────────────────
def verify(G: nx.Graph, color_map: dict) -> tuple:
    for u, v in G.edges():
        if color_map[u] == color_map[v]:
            return False, f"Conflict: {u} & {v}"
    return True, "No conflicts — schedule is valid ✓"

# ── Build slot → courses mapping ─────────────────────────────────
def build_slots(color_map: dict) -> dict:
    slots = defaultdict(list)
    for course, slot in color_map.items():
        slots[slot].append(course)
    return dict(slots)

# ── Analytics ─────────────────────────────────────────────────────
def analytics(G: nx.Graph, students: dict, color_map: dict) -> dict:
    slots = build_slots(color_map)
    deg_list   = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    edge_data  = sorted(
        [(u, v, G[u][v]["weight"]) for u, v in G.edges()],
        key=lambda x: x[2], reverse=True
    )
    heavy_stud = sorted([(n, len(c)) for n, c in students.items()],
                        key=lambda x: x[1], reverse=True)
    
    # Calculate course enrollment sizes
    course_enrollment = defaultdict(int)
    for s, courses in students.items():
        for c in courses:
            course_enrollment[c] += 1
    top_enrollment = sorted(course_enrollment.items(), key=lambda x: x[1], reverse=True)

    # Calculate students per slot (Campus Footprint)
    slot_students = defaultdict(set)
    for s, courses in students.items():
        for c in courses:
            if c in color_map:
                slot_students[color_map[c]].add(s)
    slot_students_count = {slot: len(st_set) for slot, st_set in slot_students.items()}

    slot_load  = {s: len(c) for s, c in slots.items()}
    chromatic  = max(color_map.values()) + 1 if color_map else 0
    n, e = G.number_of_nodes(), G.number_of_edges()
    density = round(2 * e / (n * (n - 1)) if n > 1 else 0, 4)

    return dict(
        deg_list=deg_list,
        edge_data=edge_data,
        heavy_stud=heavy_stud,
        top_enrollment=top_enrollment,
        slot_students_count=slot_students_count,
        slot_load=slot_load,
        chromatic=chromatic,
        density=density,
    )

# ── Split slots to reach a target day count ───────────────────────
def split_slots_to_target(slots_dict: dict, target: int) -> dict:
    """
    Splits the most-loaded slots until we reach `target` total slots.
    Safe because courses in the same slot never conflict (graph coloring guarantee).
    """
    result = {k: sorted(list(v)) for k, v in slots_dict.items()}

    while len(result) < target:
        eligible = {k: v for k, v in result.items() if len(v) >= 2}
        if not eligible:
            break  # No more splits possible
        # Pick most loaded slot
        max_slot = max(eligible, key=lambda k: len(eligible[k]))
        courses = result[max_slot]
        half = len(courses) // 2
        new_slot = max(result.keys()) + 1
        result[max_slot] = courses[:half]
        result[new_slot] = courses[half:]

    return result


# ── Score a schedule option for comfort & balance ─────────────────
def score_option(slots_dict: dict, students: dict, dated_slots: dict) -> dict:
    """
    Scores a schedule option (0-100) based on:
      - Balance: how evenly courses are spread across days
      - Max load: peak number of courses in a single day
      - Student comfort: average gap (in days) between consecutive exams
    """
    import statistics
    from datetime import date as date_obj

    courses_per_day = [len(v) for v in slots_dict.values() if v]
    n_days = len(courses_per_day)

    if n_days == 0:
        return {"combined": 0, "balance": 0, "comfort": 0, "max_load": 0,
                "avg_gap_days": 0, "days": 0}

    # 1. Balance score (lower std/mean = better)
    mean_load = statistics.mean(courses_per_day)
    if mean_load > 0 and len(courses_per_day) > 1:
        stdev = statistics.pstdev(courses_per_day)
        cv = stdev / mean_load
        balance_score = max(0.0, 1.0 - cv)
    else:
        balance_score = 1.0

    # 2. Max-load score (lower peak = better)
    max_load = max(courses_per_day)
    max_load_score = 1.0 / max_load if max_load > 0 else 1.0

    # 3. Student comfort: average gap between consecutive exam dates
    course_to_date = {}
    for date_str, courses in dated_slots.items():
        for c in courses:
            course_to_date[c] = date_str

    gaps = []
    for s_courses in students.values():
        exam_dates = sorted(
            [date_obj.fromisoformat(course_to_date[c])
             for c in s_courses if c in course_to_date]
        )
        for i in range(1, len(exam_dates)):
            gaps.append((exam_dates[i] - exam_dates[i - 1]).days)

    avg_gap = statistics.mean(gaps) if gaps else 1.0
    # Comfort normalised: 1 day = 0, 7 days = 1.0 (cap)
    comfort_score = min(avg_gap / 7.0, 1.0)

    # Combined (weighted)
    combined = (0.35 * balance_score + 0.35 * comfort_score + 0.30 * max_load_score) * 100

    return {
        "combined":     round(combined, 1),
        "balance":      round(balance_score * 100, 1),
        "comfort":      round(comfort_score * 100, 1),
        "max_load":     max_load,
        "avg_gap_days": round(avg_gap, 1),
        "days":         n_days,
    }
