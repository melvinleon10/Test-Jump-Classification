import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime
from urllib.parse import quote

# ============================================================
# FILE PATHS (single source of truth)
# ============================================================
ROOT_BASE = r"C:\Example Data\VALD Jump Exports"

ROOT_CMJ = os.path.join(ROOT_BASE, "Historical CMJ")
ROOT_SLJ = os.path.join(ROOT_BASE, "Historical SLJ")
ROOT_OVERVW = os.path.join(ROOT_BASE, "Jump History Sharing")

# Inputs
CMJ_TEAM_CSV = os.path.join(ROOT_CMJ, "Team_CMJ_Snapshot.csv")
SLJ_L_TEAM_CSV = os.path.join(ROOT_SLJ, "Team_LSLJ_Snapshot.csv")
SLJ_R_TEAM_CSV = os.path.join(ROOT_SLJ, "Team_RSLJ_Snapshot.csv")

TEAM_OVERVIEW_CSV = os.path.join(ROOT_OVERVW, "Team_AllTests_Overview.csv")

CMJ_GEN_CSV = os.path.join(ROOT_CMJ, "Generation_Daily_Classes.csv")
CMJ_ABS_CSV = os.path.join(ROOT_CMJ, "Absorption_Daily_Classes.csv")

SLJ_L_GEN_CSV = os.path.join(ROOT_SLJ, "L_Generation_Daily_Classes.csv")
SLJ_L_ABS_CSV = os.path.join(ROOT_SLJ, "L_Absorption_Daily_Classes.csv")
SLJ_R_GEN_CSV = os.path.join(ROOT_SLJ, "R_Generation_Daily_Classes.csv")
SLJ_R_ABS_CSV = os.path.join(ROOT_SLJ, "R_Absorption_Daily_Classes.csv")

# Outputs
OUTPUT_SUMMARY_CSV = os.path.join(ROOT_OVERVW, "Team_AllTests_Overview.csv")
OUTPUT_SUMMARY_PDF = os.path.join(ROOT_OVERVW, "Team_AllTests_Overview.pdf")

# HTML assets (relative paths used inside HTML)
ACCESSORIES_DIR = os.path.join(ROOT_OVERVW, "html_accessories")
ACCESSORIES_REL = "html_accessories"  # relative from ROOT_OVERVW HTML pages

# Columns
PLAYER_COL = "Name"
DATE_COL = "Date"

os.makedirs(ROOT_OVERVW, exist_ok=True)
os.makedirs(ACCESSORIES_DIR, exist_ok=True)

# ============================================================
# 1) BUILD THE TEAM OVERVIEW CSV + PDF (unchanged)
# ============================================================
cmj = pd.read_csv(CMJ_TEAM_CSV)
sljL = pd.read_csv(SLJ_L_TEAM_CSV)
sljR = pd.read_csv(SLJ_R_TEAM_CSV)

for df in [cmj, sljL, sljR]:
    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.replace("\xa0", " ", regex=False)
        .str.strip()
    )

cmj_sub = cmj[
    [
        PLAYER_COL,
        "TTD",
        "LTD",
        "BW [KG]",
        "Jump Height (Imp-Mom) [cm]",
        "Absorption_Class",
        "Generation_Class",
    ]
].copy()

cmj_sub = cmj_sub.rename(columns={"Absorption_Class": "CMJ_ABS_OVR", "Generation_Class": "CMJ_GEN_OVR"})

sljL_cols = [PLAYER_COL, "Absorption_Class_L", "Generation_Class_L"]
jhL_col = "Jump Height (Imp-Mom) [cm] (L)"
if jhL_col in sljL.columns:
    sljL_cols.insert(1, jhL_col)
sljL_sub = sljL[sljL_cols].copy().rename(
    columns={"Absorption_Class_L": "SLJ_L_ABS_OVR", "Generation_Class_L": "SLJ_L_GEN_OVR"}
)

sljR_cols = [PLAYER_COL, "Absorption_Class_R", "Generation_Class_R"]
jhR_col = "Jump Height (Imp-Mom) [cm] (R)"
if jhR_col in sljR.columns:
    sljR_cols.insert(1, jhR_col)
sljR_sub = sljR[sljR_cols].copy().rename(
    columns={"Absorption_Class_R": "SLJ_R_ABS_OVR", "Generation_Class_R": "SLJ_R_GEN_OVR"}
)

summary = cmj_sub.merge(sljL_sub, on=PLAYER_COL, how="left").merge(sljR_sub, on=PLAYER_COL, how="left")

if "LTD" in summary.columns:
    summary["_LTD_dt"] = pd.to_datetime(summary["LTD"], errors="coerce")
    summary = summary.sort_values("_LTD_dt", ascending=False).drop(columns=["_LTD_dt"])
else:
    summary = summary.sort_values(PLAYER_COL)

def classify_z(z):
    if pd.isna(z):
        return "Avg"
    if z >= 1:
        return "High"
    if z <= -1:
        return "Low"
    return "Avg"

def classify_continuous_column(df, value_col, class_col):
    if value_col not in df.columns:
        df[class_col] = "Avg"
        return df
    mean_val = df[value_col].mean()
    std_val = df[value_col].std(ddof=1)
    if std_val == 0 or pd.isna(std_val):
        df[class_col] = "Avg"
    else:
        z = (df[value_col] - mean_val) / std_val
        df[class_col] = z.apply(classify_z)
    return df

summary = classify_continuous_column(summary, "BW [KG]", "BW [KG]_class")
summary = classify_continuous_column(summary, "Jump Height (Imp-Mom) [cm]", "Jump Height (Imp-Mom) [cm]_class")
summary = classify_continuous_column(summary, "Jump Height (Imp-Mom) [cm] (L)", "Jump Height (Imp-Mom) [cm] (L)_class")
summary = classify_continuous_column(summary, "Jump Height (Imp-Mom) [cm] (R)", "Jump Height (Imp-Mom) [cm] (R)_class")

summary.to_csv(OUTPUT_SUMMARY_CSV, index=False)
print("Saved unified team overview CSV to:", OUTPUT_SUMMARY_CSV)

# ============================================================
# 2) HTML GENERATION (Team Overview + Player Pages)
# ============================================================

JS_SORT_AND_TOOLTIP = r"""
// ---------- Table Sorting ----------
function parseCellValue(text) {
    const trimmed = text.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
        return new Date(trimmed);
    }
    const num = parseFloat(trimmed);
    if (!isNaN(num)) {
        return num;
    }
    return trimmed.toLowerCase();
}
function compareValues(a, b, asc) {
    if (a === b) return 0;
    if (a > b) return asc ? 1 : -1;
    if (a < b) return asc ? -0.5 : 0.5;
    return 0;
}
function makeTablesSortable() {
    const tables = document.querySelectorAll("table.sortable-table");
    tables.forEach((table) => {
        const headers = table.querySelectorAll("thead th");
        headers.forEach((th, index) => {
            th.style.cursor = "pointer";
            th.addEventListener("click", () => {
                const tbody = table.querySelector("tbody");
                const rows = Array.from(tbody.querySelectorAll("tr"));
                const asc = th.getAttribute("data-sort") !== "asc";
                headers.forEach(h => h.removeAttribute("data-sort"));
                th.setAttribute("data-sort", asc ? "asc" : "desc");
                rows.sort((rowA, rowB) => {
                    const cellA = rowA.children[index]?.textContent || "";
                    const cellB = rowB.children[index]?.textContent || "";
                    const valA = parseCellValue(cellA);
                    const valB = parseCellValue(cellB);
                    if (valA instanceof Date && valB instanceof Date) {
                        return asc ? (valA - valB) : (valB - valA);
                    }
                    return compareValues(valA, valB, asc);
                });
                rows.forEach(r => tbody.appendChild(r));
            });
        });
    });
}

// ---------- Colored Tooltip for Metric Cells ----------
const COLOR_MAP = {
    "High": { bg: "#FF7276", text: "#840000" },
    "Low":  { bg: "#87CEEB", text: "#305CDE" },
    "Avg":  { bg: "#D3D3D3", text: "black" }
};

function createTooltip() {
    let tooltip = document.getElementById("metric-tooltip");
    if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.id = "metric-tooltip";
        tooltip.style.position = "fixed";
        tooltip.style.pointerEvents = "none";
        tooltip.style.background = "rgba(0,0,0,0.85)";
        tooltip.style.color = "white";
        tooltip.style.padding = "8px 10px";
        tooltip.style.borderRadius = "6px";
        tooltip.style.fontSize = "11px";
        tooltip.style.maxWidth = "260px";
        tooltip.style.zIndex = 9999;
        tooltip.style.display = "none";
        tooltip.style.boxShadow = "0 2px 10px rgba(0,0,0,0.25)";
        document.body.appendChild(tooltip);
    }
    return tooltip;
}
function positionTooltip(evt, tooltip) {
    const padding = 12;
    const margin = 6;
    const rect = tooltip.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    let x = evt.clientX + padding;
    let y = evt.clientY + padding;
    if (x + w + margin > window.innerWidth) x = evt.clientX - w - padding;
    if (y + h + margin > window.innerHeight) y = evt.clientY - h - padding;
    x = Math.max(margin, Math.min(x, window.innerWidth - w - margin));
    y = Math.max(margin, Math.min(y, window.innerHeight - h - margin));
    tooltip.style.left = x + "px";
    tooltip.style.top  = y + "px";
}
function showTooltip(evt, title, itemsStr) {
    const tooltip = createTooltip();
    tooltip.innerHTML = "";
    if (title && title.length > 0) {
        const titleDiv = document.createElement("div");
        titleDiv.textContent = title;
        titleDiv.style.marginBottom = "6px";
        titleDiv.style.fontWeight = "bold";
        tooltip.appendChild(titleDiv);
    }
    if (itemsStr && itemsStr.length > 0) {
        const container = document.createElement("div");
        container.style.display = "flex";
        container.style.flexWrap = "wrap";
        container.style.gap = "4px";
        const parts = itemsStr.split(";");
        parts.forEach((part) => {
            const [label, cls] = part.split("|");
            if (!label || !cls) return;
            const colors = COLOR_MAP[cls] || COLOR_MAP["Avg"];
            const chip = document.createElement("div");
            chip.textContent = label.trim();
            chip.style.padding = "2px 6px";
            chip.style.borderRadius = "4px";
            chip.style.backgroundColor = colors.bg;
            chip.style.color = colors.text;
            chip.style.fontSize = "10px";
            chip.style.whiteSpace = "nowrap";
            container.appendChild(chip);
        });
        tooltip.appendChild(container);
    }
    tooltip.style.display = "block";
    positionTooltip(evt, tooltip);
}
function hideTooltip() {
    const tooltip = document.getElementById("metric-tooltip");
    if (tooltip) tooltip.style.display = "none";
}
function attachMetricTooltips() {
    const cells = document.querySelectorAll("td.metric-cell");
    cells.forEach((cell) => {
        const title = cell.getAttribute("data-tooltip-title") || "";
        const items = cell.getAttribute("data-tooltip-items") || "";
        cell.addEventListener("mouseenter", (evt) => showTooltip(evt, title, items));
        cell.addEventListener("mousemove", (evt) => {
            const tooltip = document.getElementById("metric-tooltip");
            if (tooltip && tooltip.style.display === "block") positionTooltip(evt, tooltip);
        });
        cell.addEventListener("mouseleave", hideTooltip);
    });
}

// ---------- Pagination ----------
function initPagination() {
    const tables = document.querySelectorAll("table.paginated-table");
    tables.forEach((table) => {
        const tbody = table.querySelector("tbody");
        if (!tbody) return;
        const allRows = Array.from(tbody.querySelectorAll("tr"));
        if (allRows.length === 0) return;

        const wrapper = document.createElement("div");
        wrapper.className = "table-pagination-wrapper";
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);

        const controls = document.createElement("div");
        controls.className = "table-pagination-controls";

        const label = document.createElement("span");
        label.textContent = "Rows per page: ";

        const select = document.createElement("select");
        [10, 20, 30, 40, 50, 100, 1000].forEach((size) => {
            const opt = document.createElement("option");
            opt.value = size;
            opt.textContent = size;
            select.appendChild(opt);
        });

        const prevBtn = document.createElement("button");
        prevBtn.textContent = "<";
        const nextBtn = document.createElement("button");
        nextBtn.textContent = ">";

        const infoSpan = document.createElement("span");
        infoSpan.className = "table-pagination-info";

        controls.appendChild(label);
        controls.appendChild(select);
        controls.appendChild(prevBtn);
        controls.appendChild(nextBtn);
        controls.appendChild(infoSpan);

        wrapper.insertBefore(controls, table);

        let pageSize = parseInt(select.value, 10);
        let currentPage = 0;

        function renderPage() {
            const rows = Array.from(tbody.querySelectorAll("tr"));
            const totalRows = rows.length;
            const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
            if (currentPage >= totalPages) currentPage = totalPages - 1;
            if (currentPage < 0) currentPage = 0;
            const startIdx = currentPage * pageSize;
            const endIdx = startIdx + pageSize;
            rows.forEach((row, idx) => {
                row.style.display = (idx >= startIdx && idx < endIdx) ? "" : "none";
            });
            infoSpan.textContent = ` Page ${currentPage + 1} of ${totalPages} (total rows: ${totalRows})`;
            prevBtn.disabled = currentPage === 0;
            nextBtn.disabled = currentPage >= totalPages - 1;
        }

        select.addEventListener("change", () => {
            pageSize = parseInt(select.value, 10) || 10;
            currentPage = 0;
            renderPage();
        });
        prevBtn.addEventListener("click", () => {
            if (currentPage > 0) { currentPage--; renderPage(); }
        });
        nextBtn.addEventListener("click", () => {
            currentPage++; renderPage();
        });

        renderPage();
    });
}

// ---------- View Toggle (Summary vs Advanced) ----------
function setOverviewView(mode) {
    const summaryEls = document.querySelectorAll(".view-summary");
    const advancedEls = document.querySelectorAll(".view-advanced");
    const btnSum = document.getElementById("btn-view-summary");
    const btnAdv = document.getElementById("btn-view-advanced");

    if (mode === "summary") {
        summaryEls.forEach(el => el.style.display = "");
        advancedEls.forEach(el => el.style.display = "none");
        if (btnSum) btnSum.classList.add("active");
        if (btnAdv) btnAdv.classList.remove("active");
    } else {
        summaryEls.forEach(el => el.style.display = "none");
        advancedEls.forEach(el => el.style.display = "");
        if (btnAdv) btnAdv.classList.add("active");
        if (btnSum) btnSum.classList.remove("active");
    }
    try { localStorage.setItem("overviewViewMode", mode); } catch(e) {}
}

document.addEventListener("DOMContentLoaded", () => {
    makeTablesSortable();
    attachMetricTooltips();
    initPagination();

    let mode = "summary";
    try {
        const saved = localStorage.getItem("overviewViewMode");
        if (saved === "advanced" || saved === "summary") mode = saved;
    } catch(e) {}
    setOverviewView(mode);

    const btnSum = document.getElementById("btn-view-summary");
    const btnAdv = document.getElementById("btn-view-advanced");
    if (btnSum) btnSum.addEventListener("click", () => setOverviewView("summary"));
    if (btnAdv) btnAdv.addEventListener("click", () => setOverviewView("advanced"));
});
"""

COLOR_MAP_PY = {
    "High": {"bg": "#FF7276", "text": "#840000"},
    "Low":  {"bg": "#87CEEB", "text": "#305CDE"},
    "Avg":  {"bg": "#D3D3D3", "text": "black"},
}

def classify_color(class_val):
    v = str(class_val)
    colors = COLOR_MAP_PY.get(v, COLOR_MAP_PY["Avg"])
    return (colors["bg"], colors["text"])

def arrow_for_class(cls: str) -> str:
    c = str(cls)
    if c == "High":
        return "↑"
    if c == "Low":
        return "↓"
    if c == "Avg":
        return "-"
    return ""

def safe_player_filename(name):
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in str(name))
    safe = safe.strip().replace(" ", "_")
    return f"player_{safe}.html"

def html_escape(s):
    if s is None:
        return ""
    s = str(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#39;"))

def player_headshot_rel(player_name: str) -> str:
    return f"{ACCESSORIES_REL}/{quote(str(player_name))}.png"

DURATION_COLS = {
    "Concentric Duration [ms]",
    "Braking Phase Duration [ms]",
    "Concentric Duration [ms] (L)",
    "Braking Phase Duration [ms] (L)",
    "Concentric Duration [ms] (R)",
    "Braking Phase Duration [ms] (R)",
}
def format_number(col, val):
    try:
        x = float(val)
    except Exception:
        return str(val)
    if col in DURATION_COLS:
        return f"{round(x):.0f}"
    return f"{x:.1f}"

# ============================================================
# WORD DISPLAY (unchanged)
# ============================================================
def word_for_duration(cls: str) -> str:
    c = str(cls)
    if c == "Low":
        return "Quicker"
    if c == "High":
        return "Slower"
    return "Normal"

def word_for_force(cls: str) -> str:
    c = str(cls)
    if c == "High":
        return "Stronger"
    if c == "Low":
        return "Weaker"
    return "Normal"

def word_for_depth(cls: str) -> str:
    c = str(cls)
    if c == "High":
        return "Deeper"
    if c == "Low":
        return "Shallower"
    return "Normal"

def phrase_from_items(items, phase: str) -> str:
    label_to_cls = {lbl: cls for (lbl, cls) in items if lbl}
    if phase == "Absorption":
        dur = word_for_duration(label_to_cls.get("BD", "Avg"))
        dep = word_for_depth(label_to_cls.get("DEP", "Avg"))
        frc = word_for_force(label_to_cls.get("BF", "Avg"))
    else:
        dur = word_for_duration(label_to_cls.get("PD", "Avg"))
        dep = word_for_depth(label_to_cls.get("DEP", "Avg"))
        frc = word_for_force(label_to_cls.get("PF", "Avg"))
    return f"{dur} / {dep} / {frc}"

# ============================================================
# NEW LOGIC IMPLEMENTATION (unchanged)
# ============================================================
def classify_generation_from_components(PD, DEP, PF) -> str:
    if PD not in ["High", "Low", "Avg"] or DEP not in ["High", "Low", "Avg"] or PF not in ["High", "Low", "Avg"]:
        return ""
    if PD == "High" and DEP == "High":
        if PF in ["Avg", "Low"]: return "Low"
        if PF == "High": return "Avg"
    if PD == "Low" and DEP == "Low":
        if PF == "Avg": return "High"
        if PF == "Low": return "Avg"
        if PF == "High": return "High"
    if PD == "High" and DEP == "Avg":
        if PF in ["Avg", "Low"]: return "Low"
        if PF == "High": return "High"
    if DEP == "High" and PD == "Avg":
        if PF == "Avg": return "High"
        if PF == "Low": return "Low"
        if PF == "High": return "High"
    if PD == "Low" and DEP == "Avg":
        if PF == "Avg": return "High"
        if PF == "Low": return "Low"
        if PF == "High": return "High"
    if DEP == "Low" and PD == "Avg":
        if PF in ["Avg", "Low"]: return "Low"
        if PF == "High": return "High"
    if PD == "Avg" and DEP == "Avg":
        if PF == "High": return "High"
        if PF == "Low": return "Low"
        return "Avg"
    if PD == "Low" and DEP == "High": return "High"
    if PD == "High" and DEP == "Low": return "Low"
    return "Avg"

def classify_absorption_from_components(BD, DEP, BF) -> str:
    if BD not in ["High", "Low", "Avg"] or DEP not in ["High", "Low", "Avg"] or BF not in ["High", "Low", "Avg"]:
        return ""
    if BD == "High" and DEP == "High":
        if BF in ["Avg", "Low"]: return "High"
        if BF == "High": return "Avg"
    if BD == "Low" and DEP == "Low":
        if BF == "Avg": return "Low"
        if BF == "Low": return "Avg"
        if BF == "High": return "Low"
    if BD == "High" and DEP == "Avg":
        if BF in ["Avg", "Low"]: return "Low"
        if BF == "High": return "High"
    if DEP == "High" and BD == "Avg":
        if BF == "Avg": return "High"
        if BF == "Low": return "Low"
        if BF == "High": return "High"
    if BD == "Low" and DEP == "Avg":
        if BF == "Avg": return "High"
        if BF == "Low": return "Low"
        if BF == "High": return "High"
    if DEP == "Low" and BD == "Avg":
        if BF in ["Avg", "Low"]: return "Low"
        if BF == "High": return "High"
    if BD == "Avg" and DEP == "Avg":
        if BF == "High": return "High"
        if BF == "Low": return "Low"
        return "Avg"
    if BD == "Low" and DEP == "High": return "High"
    if BD == "High" and DEP == "Low": return "Low"
    return "Avg"

# ============================================================
# LOAD TEAM OVERVIEW (CSV created above)
# ============================================================
team_df = pd.read_csv(TEAM_OVERVIEW_CSV)
if "LTD" in team_df.columns:
    team_df["LTD_dt"] = pd.to_datetime(team_df["LTD"], errors="coerce")
    team_df = team_df.sort_values("LTD_dt", ascending=False).drop(columns=["LTD_dt"])
else:
    team_df = team_df.sort_values(PLAYER_COL)

# ============================================================
# LOAD DAILY FILES
# ============================================================
def load_daily(file_path, label):
    if not os.path.exists(file_path):
        print(f"WARNING: {label} file not found at {file_path}.")
        return pd.DataFrame()
    df = pd.read_csv(file_path)
    df.columns = (
        df.columns.astype(str)
          .str.replace("\ufeff", "", regex=False)
          .str.replace("\xa0", " ", regex=False)
          .str.strip()
    )
    if DATE_COL in df.columns:
        df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    return df

cmj_gen = load_daily(CMJ_GEN_CSV, "CMJ Generation")
cmj_abs = load_daily(CMJ_ABS_CSV, "CMJ Absorption")
sljL_gen = load_daily(SLJ_L_GEN_CSV, "SLJ-L Generation")
sljL_abs = load_daily(SLJ_L_ABS_CSV, "SLJ-L Absorption")
sljR_gen = load_daily(SLJ_R_GEN_CSV, "SLJ-R Generation")
sljR_abs = load_daily(SLJ_R_ABS_CSV, "SLJ-R Absorption")

def merge_daily(gen_df, abs_df):
    if gen_df.empty and abs_df.empty:
        return pd.DataFrame()
    if gen_df.empty:
        return abs_df.copy()
    if abs_df.empty:
        return gen_df.copy()
    return pd.merge(gen_df, abs_df, on=[PLAYER_COL, DATE_COL], how="outer", suffixes=("_GEN", "_ABS"))

def coalesce_columns(df, base_name):
    if base_name not in df.columns:
        for cand in [base_name + "_GEN", base_name + "_ABS", base_name + "_x", base_name + "_y"]:
            if cand in df.columns:
                df[base_name] = df[cand]
                break
    class_base = base_name + "_class"
    if class_base not in df.columns:
        for cand in [class_base + "_GEN", class_base + "_ABS", class_base + "_x", class_base + "_y"]:
            if cand in df.columns:
                df[class_base] = df[cand]
                break
    avg_prev = base_name + "_avg_prev"
    if avg_prev not in df.columns:
        for cand in [avg_prev + "_GEN", avg_prev + "_ABS", avg_prev + "_x", avg_prev + "_y"]:
            if cand in df.columns:
                df[avg_prev] = df[cand]
                break

def coalesce_simple(df, col_base):
    if col_base in df.columns:
        return
    for cand in [col_base + "_GEN", col_base + "_ABS", col_base + "_x", col_base + "_y"]:
        if cand in df.columns:
            df[col_base] = df[cand]
            break

def standardize_test_df(df, test_type):
    if df.empty:
        return df

    if test_type == "CMJ":
        bases = [
            "Concentric Duration [ms]",
            "Concentric Mean Force / BM [N/kg]",
            "Braking Phase Duration [ms]",
            "Countermovement Depth [cm]",
            "Eccentric Mean Force / BM [N/kg]",
            "BW [KG]",
            "Jump Height (Imp-Mom) [cm]",
        ]
    elif test_type == "SLJ_L":
        bases = [
            "Concentric Duration [ms] (L)",
            "Concentric Mean Force / BM [N/kg] (L)",
            "Braking Phase Duration [ms] (L)",
            "Countermovement Depth [cm] (L)",
            "Eccentric Mean Force / BM [N/kg] (L)",
            "BW [KG]",
            "Jump Height (Imp-Mom) [cm] (L)",
        ]
    else:
        bases = [
            "Concentric Duration [ms] (R)",
            "Concentric Mean Force / BM [N/kg] (R)",
            "Braking Phase Duration [ms] (R)",
            "Countermovement Depth [cm] (R)",
            "Eccentric Mean Force / BM [N/kg] (R)",
            "BW [KG]",
            "Jump Height (Imp-Mom) [cm] (R)",
        ]

    for b in bases:
        coalesce_columns(df, b)

    coalesce_simple(df, "Generation_Class")
    coalesce_simple(df, "Absorption_Class")

    if test_type == "SLJ_L":
        if "Generation_Class" not in df.columns and "Generation_Class_L" in df.columns:
            df["Generation_Class"] = df["Generation_Class_L"]
        if "Absorption_Class" not in df.columns and "Absorption_Class_L" in df.columns:
            df["Absorption_Class"] = df["Absorption_Class_L"]

    if test_type == "SLJ_R":
        if "Generation_Class" not in df.columns and "Generation_Class_R" in df.columns:
            df["Generation_Class"] = df["Generation_Class_R"]
        if "Absorption_Class" not in df.columns and "Absorption_Class_R" in df.columns:
            df["Absorption_Class"] = df["Absorption_Class_R"]

    return df

cmj_daily = standardize_test_df(merge_daily(cmj_gen, cmj_abs), "CMJ")
sljL_daily = standardize_test_df(merge_daily(sljL_gen, sljL_abs), "SLJ_L")
sljR_daily = standardize_test_df(merge_daily(sljR_gen, sljR_abs), "SLJ_R")

def recompute_overall_phase_classes(df_daily, test_type: str):
    if df_daily is None or df_daily.empty:
        return df_daily

    if test_type == "CMJ":
        pd_col = "Concentric Duration [ms]"
        pf_col = "Concentric Mean Force / BM [N/kg]"
        bd_col = "Braking Phase Duration [ms]"
        dep_col = "Countermovement Depth [cm]"
        bf_col = "Eccentric Mean Force / BM [N/kg]"
    elif test_type == "SLJ_L":
        pd_col = "Concentric Duration [ms] (L)"
        pf_col = "Concentric Mean Force / BM [N/kg] (L)"
        bd_col = "Braking Phase Duration [ms] (L)"
        dep_col = "Countermovement Depth [cm] (L)"
        bf_col = "Eccentric Mean Force / BM [N/kg] (L)"
    else:
        pd_col = "Concentric Duration [ms] (R)"
        pf_col = "Concentric Mean Force / BM [N/kg] (R)"
        bd_col = "Braking Phase Duration [ms] (R)"
        dep_col = "Countermovement Depth [cm] (R)"
        bf_col = "Eccentric Mean Force / BM [N/kg] (R)"

    def cls_of(row, base):
        return row.get(f"{base}_class", "")

    if all(f"{c}_class" in df_daily.columns for c in [pd_col, dep_col, pf_col]):
        df_daily["Generation_Class"] = df_daily.apply(
            lambda r: classify_generation_from_components(cls_of(r, pd_col), cls_of(r, dep_col), cls_of(r, pf_col)),
            axis=1
        )

    if all(f"{c}_class" in df_daily.columns for c in [bd_col, dep_col, bf_col]):
        df_daily["Absorption_Class"] = df_daily.apply(
            lambda r: classify_absorption_from_components(cls_of(r, bd_col), cls_of(r, dep_col), cls_of(r, bf_col)),
            axis=1
        )

    return df_daily

cmj_daily = recompute_overall_phase_classes(cmj_daily, "CMJ")
sljL_daily = recompute_overall_phase_classes(sljL_daily, "SLJ_L")
sljR_daily = recompute_overall_phase_classes(sljR_daily, "SLJ_R")

# ============================================================
# Helper funcs used by HTML build
# ============================================================
def get_param_mean(player, test_type, param_col):
    df = cmj_daily if test_type == "CMJ" else sljL_daily if test_type == "SLJ_L" else sljR_daily
    if df is None or df.empty or param_col not in df.columns:
        return None
    sub = df[df[PLAYER_COL] == player]
    if sub.empty:
        return None
    m = pd.to_numeric(sub[param_col], errors="coerce").mean()
    return None if pd.isna(m) else m

def get_latest_param_class(player, test_type, param_col):
    df = cmj_daily if test_type == "CMJ" else sljL_daily if test_type == "SLJ_L" else sljR_daily
    if df is None or df.empty or param_col not in df.columns:
        return None
    sub = df[df[PLAYER_COL] == player].copy()
    if sub.empty:
        return None
    sub = sub.sort_values(DATE_COL)
    last = sub.iloc[-1]
    return last.get(f"{param_col}_class", None)

def get_latest_bw_jh_class(player):
    if cmj_daily.empty:
        return (None, None)
    sub = cmj_daily[cmj_daily[PLAYER_COL] == player].copy()
    if sub.empty:
        return (None, None)
    sub = sub.sort_values(DATE_COL)
    last = sub.iloc[-1]
    return (last.get("BW [KG]_class", None), last.get("Jump Height (Imp-Mom) [cm]_class", None))

def get_latest_phase_components(player, test_type, phase):
    df = cmj_daily if test_type == "CMJ" else sljL_daily if test_type == "SLJ_L" else sljR_daily
    if df is None or df.empty:
        return ("", [])

    if test_type == "CMJ":
        pd_col = "Concentric Duration [ms]"
        pf_col = "Concentric Mean Force / BM [N/kg]"
        bd_col = "Braking Phase Duration [ms]"
        dep_col = "Countermovement Depth [cm]"
        bf_col = "Eccentric Mean Force / BM [N/kg]"
    elif test_type == "SLJ_L":
        pd_col = "Concentric Duration [ms] (L)"
        pf_col = "Concentric Mean Force / BM [N/kg] (L)"
        bd_col = "Braking Phase Duration [ms] (L)"
        dep_col = "Countermovement Depth [cm] (L)"
        bf_col = "Eccentric Mean Force / BM [N/kg] (L)"
    else:
        pd_col = "Concentric Duration [ms] (R)"
        pf_col = "Concentric Mean Force / BM [N/kg] (R)"
        bd_col = "Braking Phase Duration [ms] (R)"
        dep_col = "Countermovement Depth [cm] (R)"
        bf_col = "Eccentric Mean Force / BM [N/kg] (R)"

    sub = df[df[PLAYER_COL] == player].copy()
    if sub.empty:
        return ("", [])

    sub = sub.sort_values(DATE_COL)
    last = sub.iloc[-1]
    date_val = last.get(DATE_COL, None)
    date_str = date_val.strftime("%Y-%m-%d") if isinstance(date_val, pd.Timestamp) else ""

    def get_class(col_name):
        return last.get(f"{col_name}_class", "")

    if phase == "Generation":
        return (date_str, [("PD", get_class(pd_col)), ("DEP", get_class(dep_col)), ("PF", get_class(pf_col))])
    return (date_str, [("BD", get_class(bd_col)), ("DEP", get_class(dep_col)), ("BF", get_class(bf_col))])

# ============================================================
# TEAM OVERVIEW HTML
# ============================================================
def build_team_overview_html(df: pd.DataFrame, out_path: str):
    cols = [
        PLAYER_COL, "TTD", "LTD",
        "BW [KG]",
        "Jump Height (Imp-Mom) [cm]",
        "Jump Height (Imp-Mom) [cm] (L)",
        "Jump Height (Imp-Mom) [cm] (R)",
        "CMJ_ABS_OVR", "CMJ_GEN_OVR",
        "SLJ_L_ABS_OVR", "SLJ_L_GEN_OVR",
        "SLJ_R_ABS_OVR", "SLJ_R_GEN_OVR",
    ]

    display_labels = {
        PLAYER_COL: "PLAYER",
        "TTD": "Total\nTesting Days",
        "LTD": "Last\nTesting Day",
        "BW [KG]": "Weight [kg]",
        "Jump Height (Imp-Mom) [cm]": "CMJ\nJump Height [cm]",
        "Jump Height (Imp-Mom) [cm] (L)": "SLJ-L\nJump Height [cm]",
        "Jump Height (Imp-Mom) [cm] (R)": "SLJ-R\nJump Height [cm]",
        "CMJ_ABS_OVR": "CMJ\nAbsorption",
        "CMJ_GEN_OVR": "CMJ\nGeneration",
        "SLJ_L_ABS_OVR": "SLJ-L\nAbsorption",
        "SLJ_L_GEN_OVR": "SLJ-L\nGeneration",
        "SLJ_R_ABS_OVR": "SLJ-R\nAbsorption",
        "SLJ_R_GEN_OVR": "SLJ-R\nGeneration",
    }

    metric_phase_map = {
        "CMJ_ABS_OVR":   ("CMJ",   "Absorption"),
        "CMJ_GEN_OVR":   ("CMJ",   "Generation"),
        "SLJ_L_ABS_OVR": ("SLJ_L", "Absorption"),
        "SLJ_L_GEN_OVR": ("SLJ_L", "Generation"),
        "SLJ_R_ABS_OVR": ("SLJ_R", "Absorption"),
        "SLJ_R_GEN_OVR": ("SLJ_R", "Generation"),
    }

    header_cells = "".join(f"<th>{display_labels.get(c, c)}</th>" for c in cols)

    html_rows = []
    for _, row in df.iterrows():
        player = row.get(PLAYER_COL, "")
        player_filename = safe_player_filename(player)

        row_bw_cls = row.get("BW [KG]_class", None)
        row_cmj_jh_cls = row.get("Jump Height (Imp-Mom) [cm]_class", None)
        row_sljL_jh_cls = row.get("Jump Height (Imp-Mom) [cm] (L)_class", None)
        row_sljR_jh_cls = row.get("Jump Height (Imp-Mom) [cm] (R)_class", None)

        fallback_bw_cls, fallback_jh_cls = get_latest_bw_jh_class(player)
        if row_bw_cls not in ["High", "Low", "Avg"]:
            row_bw_cls = fallback_bw_cls
        if row_cmj_jh_cls not in ["High", "Low", "Avg"]:
            row_cmj_jh_cls = fallback_jh_cls

        if row_sljL_jh_cls not in ["High", "Low", "Avg"]:
            row_sljL_jh_cls = get_latest_param_class(player, "SLJ_L", "Jump Height (Imp-Mom) [cm] (L)")
        if row_sljR_jh_cls not in ["High", "Low", "Avg"]:
            row_sljR_jh_cls = get_latest_param_class(player, "SLJ_R", "Jump Height (Imp-Mom) [cm] (R)")

        mean_bw_cmj = get_param_mean(player, "CMJ", "BW [KG]")
        mean_jh_cmj = get_param_mean(player, "CMJ", "Jump Height (Imp-Mom) [cm]")
        mean_jh_sljL = get_param_mean(player, "SLJ_L", "Jump Height (Imp-Mom) [cm] (L)")
        mean_jh_sljR = get_param_mean(player, "SLJ_R", "Jump Height (Imp-Mom) [cm] (R)")

        row_tds = []
        for col in cols:
            val = row.get(col, "")
            val_str = "" if pd.isna(val) else str(val)

            if col == PLAYER_COL:
                img_src = player_headshot_rel(val_str)
                row_tds.append(
                    f'<td class="sticky-name">'
                    f'  <a class="player-link" href="{player_filename}">'
                    f'    <img class="player-avatar" src="{img_src}" alt="{html_escape(val_str)}" '
                    f'         onerror="this.style.display=\'none\';" />'
                    f'    <span class="player-name-text">{html_escape(val_str)}</span>'
                    f'  </a>'
                    f'</td>'
                )
                continue

            if col == "BW [KG]":
                bg, fg = classify_color(row_bw_cls)
                title = f"CMJ Body Weight - mean: {mean_bw_cmj:.1f} kg" if mean_bw_cmj is not None else "CMJ Body Weight - no historical mean"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm]":
                bg, fg = classify_color(row_cmj_jh_cls)
                title = f"CMJ Jump Height - mean: {mean_jh_cmj:.1f} cm" if mean_jh_cmj is not None else "CMJ Jump Height - no historical mean"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm] (L)":
                bg, fg = classify_color(row_sljL_jh_cls)
                title = f"SLJ-L Jump Height - mean: {mean_jh_sljL:.1f} cm" if mean_jh_sljL is not None else "SLJ-L Jump Height - no historical mean"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm] (R)":
                bg, fg = classify_color(row_sljR_jh_cls)
                title = f"SLJ-R Jump Height - mean: {mean_jh_sljR:.1f} cm" if mean_jh_sljR is not None else "SLJ-R Jump Height - no historical mean"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">{html_escape(val_str)}</td>'
                )
                continue

            if col in metric_phase_map:
                test_type, phase = metric_phase_map[col]
                bg, fg = classify_color(val_str)

                date_str, items = get_latest_phase_components(player, test_type, phase)
                items_str = ";".join(f"{lbl}|{cls}" for (lbl, cls) in items if lbl and cls)
                tooltip_title = f"{test_type} {phase} ({date_str})"

                summary_disp = arrow_for_class(val_str)
                advanced_disp = phrase_from_items(items, phase)

                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(tooltip_title)}" data-tooltip-items="{html_escape(items_str)}">'
                    f'  <span class="view-summary" style="font-weight:900;font-size:16px;line-height:1;">{html_escape(summary_disp)}</span>'
                    f'  <span class="view-advanced" style="display:none;">{html_escape(advanced_disp)}</span>'
                    f'</td>'
                )
                continue

            row_tds.append(f"<td>{html_escape(val_str)}</td>")

        html_rows.append("<tr>" + "".join(row_tds) + "</tr>")

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Team CMJ / SLJ Overview</title>
<style>
:root {{
    --primary-100:#CE0E2D;
    --primary-200:#CE0E2D;
    --primary-300:#CE0E2D;
    --accent-100:#FFFFFF;
    --accent-200:#9b9b9b;
    --text-100:#FFFFFF;
    --text-200:#e0e0e0;
    --bg-100:#0A2240;
    --bg-200:#3A8DDE;
    --bg-300:#3A8DDE;
}}

body {{
    font-family: Arial, sans-serif;
    margin: 20px;
    background: var(--bg-100);
    color: var(--text-100);
}}

table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
    font-size: 12px;
    background: rgba(255,255,255,0.06);
}}

th, td {{
    border: 1px solid rgba(255,255,255,0.18);
    padding: 4px 6px;
    text-align: center;
    word-wrap: break-word;
}}

th {{
    background-color: var(--bg-300);
    color: var(--text-100);
    position: sticky;
    top: 0;
    z-index: 2;
}}

.sticky-name {{
    position: sticky;
    left: 0;
    background-color: var(--bg-200);
    z-index: 1;
    text-align: left;
}}

a {{
    color: inherit;
    text-decoration: none;
    font-weight: bold;
}}

a:hover {{ text-decoration: underline; }}

tbody tr:nth-child(even) {{ background-color: rgba(255,255,255,0.06); }}
tbody tr:nth-child(odd)  {{ background-color: rgba(255,255,255,0.03); }}

.player-link {{ display: inline-flex; align-items: center; gap: 8px; }}

.player-avatar {{
    width: 22px;
    height: 22px;
    border-radius: 50%;
    object-fit: cover;
    border: 1px solid rgba(255,255,255,0.35);
    flex: 0 0 auto;
    background: rgba(255,255,255,0.08);
}}

.player-name-text {{ display: inline-block; }}

h1 {{ color: var(--text-100); }}
p  {{ color: var(--text-200); }}

.topbar {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
}}
.view-toggle {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 10px;
    background: rgba(255,255,255,0.08);
}}
.view-toggle .label {{
    font-size: 11px;
    color: var(--text-200);
    margin-right: 4px;
}}
.view-toggle button {{
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.18);
    background: rgba(255,255,255,0.10);
    color: var(--text-100);
    cursor: pointer;
}}
.view-toggle button.active {{
    background: var(--primary-200);
    border-color: rgba(0,0,0,0.0);
}}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <h1>CMJ & SLJ Team Overview</h1>
    <p>
      Hover over Absorption & Generation cells to see component classes.
      Click a player name to open their history.
      Use the toggle to switch between Summary vs Advanced.
    </p>
  </div>

  <div class="view-toggle" title="Switch between arrow view and word view">
    <span class="label">View:</span>
    <button id="btn-view-summary" type="button">Summary</button>
    <button id="btn-view-advanced" type="button">Advanced</button>
  </div>
</div>

<table class="sortable-table">
    <thead><tr>{header_cells}</tr></thead>
    <tbody>{"".join(html_rows)}</tbody>
</table>

<script>
{JS_SORT_AND_TOOLTIP}
</script>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved team overview HTML to:", out_path)

# ============================================================
# PLAYER HISTORY HTML
# ============================================================
def build_player_history_html(player, out_path):
    sections = []

    def ensure_class_column(sub, value_col, class_col):
        if class_col in sub.columns or value_col not in sub.columns:
            return sub
        sub[class_col] = "Avg"
        return sub

    def get_row_phase_items(row, test_type, phase):
        if test_type == "CMJ":
            pd_col = "Concentric Duration [ms]"
            pf_col = "Concentric Mean Force / BM [N/kg]"
            bd_col = "Braking Phase Duration [ms]"
            dep_col = "Countermovement Depth [cm]"
            bf_col = "Eccentric Mean Force / BM [N/kg]"
        elif test_type == "SLJ_L":
            pd_col = "Concentric Duration [ms] (L)"
            pf_col = "Concentric Mean Force / BM [N/kg] (L)"
            bd_col = "Braking Phase Duration [ms] (L)"
            dep_col = "Countermovement Depth [cm] (L)"
            bf_col = "Eccentric Mean Force / BM [N/kg] (L)"
        else:
            pd_col = "Concentric Duration [ms] (R)"
            pf_col = "Concentric Mean Force / BM [N/kg] (R)"
            bd_col = "Braking Phase Duration [ms] (R)"
            dep_col = "Countermovement Depth [cm] (R)"
            bf_col = "Eccentric Mean Force / BM [N/kg] (R)"

        if phase == "Generation":
            items = [("PD", row.get(f"{pd_col}_class", "")),
                     ("DEP", row.get(f"{dep_col}_class", "")),
                     ("PF", row.get(f"{pf_col}_class", ""))]
        else:
            items = [("BD", row.get(f"{bd_col}_class", "")),
                     ("DEP", row.get(f"{dep_col}_class", "")),
                     ("BF", row.get(f"{bf_col}_class", ""))]

        clean = []
        for lbl, cls in items:
            if cls is None or str(cls) == "nan":
                cls = ""
            clean.append((lbl, str(cls)))
        return clean

    def tooltip_for_avg_prev(row, value_col, label):
        avg_col = f"{value_col}_avg_prev"
        avg_val = row.get(avg_col, None)
        if avg_val is None or (isinstance(avg_val, float) and pd.isna(avg_val)) or str(avg_val) == "nan":
            return f"{label} mean: N/A (first test)"
        try:
            avg_str = format_number(value_col, avg_val)
        except Exception:
            avg_str = str(avg_val)
        return f"{label} mean: {avg_str}"

    def build_section(title, df_daily, test_type):
        if df_daily is None or df_daily.empty:
            return f"<h2>{html_escape(title)}</h2><p>No data available.</p>"

        sub = df_daily[df_daily[PLAYER_COL] == player].copy()
        if sub.empty:
            return f"<h2>{html_escape(title)}</h2><p>No data available.</p>"

        sub = sub.sort_values(DATE_COL, ascending=False)

        for col in ["Generation_Class", "Absorption_Class"]:
            if col not in sub.columns:
                for cand in [col + "_GEN", col + "_ABS", col + "_x", col + "_y", col + "_L", col + "_R"]:
                    if cand in sub.columns:
                        sub[col] = sub[cand]
                        break

        if test_type == "CMJ":
            param_specs = [
                {"value_col": "BW [KG]", "class_col": "BW [KG]_class", "label": "Body Weight [kg]"},
                {"value_col": "Jump Height (Imp-Mom) [cm]", "class_col": "Jump Height (Imp-Mom) [cm]_class", "label": "Jump Height [cm]"},
                {"value_col": "Braking Phase Duration [ms]", "class_col": "Braking Phase Duration [ms]_class", "label": "Braking Duration [ms]"},
                {"value_col": "Countermovement Depth [cm]", "class_col": "Countermovement Depth [cm]_class", "label": "Squat Depth [cm]"},
                {"value_col": "Eccentric Mean Force / BM [N/kg]", "class_col": "Eccentric Mean Force / BM [N/kg]_class", "label": "Braking Force [N/kg]"},
                {"value_col": "Concentric Duration [ms]", "class_col": "Concentric Duration [ms]_class", "label": "Propulsive Duration [ms]"},
                {"value_col": "Concentric Mean Force / BM [N/kg]", "class_col": "Concentric Mean Force / BM [N/kg]_class", "label": "Propulsive Force [N/kg]"},
            ]
        elif test_type == "SLJ_L":
            param_specs = [
                {"value_col": "BW [KG]", "class_col": "BW [KG]_class", "label": "Body Weight [kg]"},
                {"value_col": "Jump Height (Imp-Mom) [cm] (L)", "class_col": "Jump Height (Imp-Mom) [cm] (L)_class", "label": "Jump Height [cm]"},
                {"value_col": "Braking Phase Duration [ms] (L)", "class_col": "Braking Phase Duration [ms] (L)_class", "label": "Braking Duration [ms]"},
                {"value_col": "Countermovement Depth [cm] (L)", "class_col": "Countermovement Depth [cm] (L)_class", "label": "Squat Depth [cm]"},
                {"value_col": "Eccentric Mean Force / BM [N/kg] (L)", "class_col": "Eccentric Mean Force / BM [N/kg] (L)_class", "label": "Braking Force [N/kg]"},
                {"value_col": "Concentric Duration [ms] (L)", "class_col": "Concentric Duration [ms] (L)_class", "label": "Propulsive Duration [ms]"},
                {"value_col": "Concentric Mean Force / BM [N/kg] (L)", "class_col": "Concentric Mean Force / BM [N/kg] (L)_class", "label": "Propulsive Force [N/kg]"},
            ]
        else:
            param_specs = [
                {"value_col": "BW [KG]", "class_col": "BW [KG]_class", "label": "Body Weight [kg]"},
                {"value_col": "Jump Height (Imp-Mom) [cm] (R)", "class_col": "Jump Height (Imp-Mom) [cm] (R)_class", "label": "Jump Height [cm]"},
                {"value_col": "Braking Phase Duration [ms] (R)", "class_col": "Braking Phase Duration [ms] (R)_class", "label": "Braking Duration [ms]"},
                {"value_col": "Countermovement Depth [cm] (R)", "class_col": "Countermovement Depth [cm] (R)_class", "label": "Squat Depth [cm]"},
                {"value_col": "Eccentric Mean Force / BM [N/kg] (R)", "class_col": "Eccentric Mean Force / BM [N/kg] (R)_class", "label": "Braking Force [N/kg]"},
                {"value_col": "Concentric Duration [ms] (R)", "class_col": "Concentric Duration [ms] (R)_class", "label": "Propulsive Duration [ms]"},
                {"value_col": "Concentric Mean Force / BM [N/kg] (R)", "class_col": "Concentric Mean Force / BM [N/kg] (R)_class", "label": "Propulsive Force [N/kg]"},
            ]

        for spec in param_specs:
            sub = ensure_class_column(sub, spec["value_col"], spec["class_col"])

        gen_col = "Generation_Class"
        abs_col = "Absorption_Class"
        cols = [DATE_COL, abs_col, gen_col] + [spec["value_col"] for spec in param_specs]
        value_col_map = {spec["value_col"]: spec for spec in param_specs}
        numeric_cols = set(value_col_map.keys())

        header_cells = []
        for c in cols:
            if c == DATE_COL:
                header_cells.append("<th>Date</th>")
            elif c == gen_col:
                header_cells.append("<th>Generation Overall</th>")
            elif c == abs_col:
                header_cells.append("<th>Absorption Overall</th>")
            else:
                header_cells.append(f"<th>{html_escape(value_col_map[c]['label'])}</th>")

        body_rows = []
        for _, r in sub.iterrows():
            date_val = r.get(DATE_COL, None)
            date_str = date_val.strftime("%Y-%m-%d") if isinstance(date_val, pd.Timestamp) else ""
            tds = []

            for c in cols:
                v = r.get(c, "")

                if c == DATE_COL:
                    tds.append(f"<td>{html_escape(date_str)}</td>")
                    continue

                # ---- UPDATED: Abs/Gen cells support Summary(arrow) + Advanced(words) ----
                if c in [gen_col, abs_col]:
                    cls_val = "" if pd.isna(v) else str(v)
                    bg, fg = classify_color(cls_val)
                    phase = "Generation" if c == gen_col else "Absorption"

                    items = get_row_phase_items(r, test_type, phase)
                    items_str = ";".join(f"{lbl}|{cls}" for (lbl, cls) in items if lbl and cls)
                    tooltip_title = f"{test_type} {phase} ({date_str})"

                    summary_disp = arrow_for_class(cls_val)
                    advanced_disp = phrase_from_items(items, phase)

                    tds.append(
                        f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                        f'data-tooltip-title="{html_escape(tooltip_title)}" data-tooltip-items="{html_escape(items_str)}">'
                        f'  <span class="view-summary" style="font-weight:900;font-size:16px;line-height:1;">{html_escape(summary_disp)}</span>'
                        f'  <span class="view-advanced" style="display:none;">{html_escape(advanced_disp)}</span>'
                        f'</td>'
                    )
                    continue

                if c in numeric_cols:
                    v_str = "" if pd.isna(v) else format_number(c, v)
                    cls_val = r.get(value_col_map[c]["class_col"], "Avg")
                    bg, fg = classify_color(cls_val)
                    tt_title = tooltip_for_avg_prev(r, c, value_col_map[c]["label"])
                    tds.append(
                        f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                        f'data-tooltip-title="{html_escape(tt_title)}" data-tooltip-items="">{html_escape(v_str)}</td>'
                    )
                    continue

                tds.append(f"<td>{html_escape(v)}</td>")

            body_rows.append("<tr>" + "".join(tds) + "</tr>")

        return f"""
<h2>{html_escape(title)}</h2>
<table class="sortable-table paginated-table">
    <thead><tr>{"".join(header_cells)}</tr></thead>
    <tbody>{"".join(body_rows)}</tbody>
</table>
"""

    sections.append(build_section("CMJ", cmj_daily, "CMJ"))
    sections.append(build_section("SLJ - Left", sljL_daily, "SLJ_L"))
    sections.append(build_section("SLJ - Right", sljR_daily, "SLJ_R"))

    player_img = player_headshot_rel(player)

    full_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html_escape(player)} - Jump History</title>
<style>
:root {{
    --primary-100:#CE0E2D;
    --primary-200:#CE0E2D;
    --primary-300:#CE0E2D;
    --accent-100:#FFFFFF;
    --accent-200:#9b9b9b;
    --text-100:#FFFFFF;
    --text-200:#e0e0e0;
    --bg-100:#0A2240;
    --bg-200:#3A8DDE;
    --bg-300:#3A8DDE;
}}

body {{
    font-family: Arial, sans-serif;
    margin: 20px;
    background: var(--bg-100);
    color: var(--text-100);
}}

.page-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
}}

.back-link {{
    display: inline-block;
    margin-top: 8px;
    color: var(--primary-200);
    text-decoration: none;
}}

.back-link:hover {{ text-decoration: underline; }}

.player-identity {{ display: flex; align-items: center; gap: 10px; }}

.player-identity img {{
    width: 48px;
    height: 48px;
    border-radius: 50%;
    object-fit: cover;
    border: 1px solid rgba(255,255,255,0.35);
    background: rgba(255,255,255,0.08);
}}

.player-identity-name {{
    font-weight: 800;
    font-size: 16px;
    white-space: nowrap;
}}

.topbar {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin: 10px 0 12px 0;
}}

.view-toggle {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 10px;
    background: rgba(255,255,255,0.08);
}}
.view-toggle .label {{
    font-size: 11px;
    color: var(--text-200);
    margin-right: 4px;
}}
.view-toggle button {{
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.18);
    background: rgba(255,255,255,0.10);
    color: var(--text-100);
    cursor: pointer;
}}
.view-toggle button.active {{
    background: var(--primary-200);
    border-color: rgba(0,0,0,0.0);
}}

.table-pagination-controls {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
    font-size: 12px;
    color: var(--text-200);
}}

.table-pagination-controls select {{
    font-size: 12px;
    background: rgba(255,255,255,0.10);
    color: var(--text-100);
    border: 1px solid rgba(255,255,255,0.18);
}}

.table-pagination-controls button {{
    font-size: 11px;
    padding: 2px 6px;
    background: rgba(255,255,255,0.10);
    color: var(--text-100);
    border: 1px solid rgba(255,255,255,0.18);
}}

table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: auto;
    font-size: 12px;
    margin-bottom: 20px;
    background: rgba(255,255,255,0.06);
}}

th, td {{
    border: 1px solid rgba(255,255,255,0.18);
    padding: 4px 6px;
    text-align: center;
}}

th {{
    background-color: var(--bg-300);
    color: var(--text-100);
}}

tbody tr:nth-child(even) {{ background-color: rgba(255,255,255,0.06); }}
tbody tr:nth-child(odd)  {{ background-color: rgba(255,255,255,0.03); }}

h1, h2 {{ color: var(--text-100); }}
p {{ color: var(--text-200); }}
</style>
</head>
<body>

<div class="page-header">
    <div>
        <h1>Jump History</h1>
        <a class="back-link" href="index.html">&larr; Back to Team Overview</a>
    </div>
    <div class="player-identity">
        <img src="{player_img}" alt="{html_escape(player)}" onerror="this.style.display='none';" />
        <div class="player-identity-name">{html_escape(player)}</div>
    </div>
</div>

<div class="topbar">
  <div>
    <p style="margin:0;">
      Toggle Summary vs Advanced
    </p>
  </div>
  <div class="view-toggle" title="Switch between arrow view and word view">
    <span class="label">View:</span>
    <button id="btn-view-summary" type="button">Summary</button>
    <button id="btn-view-advanced" type="button">Advanced</button>
  </div>
</div>

{"".join(sections)}

<script>
{JS_SORT_AND_TOOLTIP}
</script>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print("Saved player page:", out_path)

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    index_path = os.path.join(ROOT_OVERVW, "index.html")
    build_team_overview_html(team_df, index_path)

    players = team_df[PLAYER_COL].dropna().unique()
    for p in players:
        out_path = os.path.join(ROOT_OVERVW, safe_player_filename(p))
        build_player_history_html(p, out_path)
