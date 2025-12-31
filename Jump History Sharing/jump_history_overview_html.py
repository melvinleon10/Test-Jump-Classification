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
# 2) HTML GENERATION
# ============================================================

# ============================================================
# EDIT 1: Tooltip system now supports different content by view
# - Summary: keep your existing Abs/Gen tooltip chips (perfect)
# - Advanced: Abs/Gen tooltip shows "BD/PD: value (Z:__)" etc, colored by class
# - All other parameter tooltips (means) remain unchanged in both views
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

// ---------- Colored Tooltip ----------
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
        tooltip.style.maxWidth = "320px";
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

// ---------- View Mode State ----------
let __overviewViewMode = "summary";
function getViewMode() {
    return __overviewViewMode || "summary";
}

// ---------- Tooltip attachment (view-aware for Abs/Gen) ----------
function attachMetricTooltips() {
    const cells = document.querySelectorAll("td.metric-cell");
    cells.forEach((cell) => {
        cell.addEventListener("mouseenter", (evt) => {
            const mode = getViewMode();

            // Prefer view-specific tooltip fields when present:
            const title = (mode === "advanced")
                ? (cell.getAttribute("data-tooltip-title-advanced") || cell.getAttribute("data-tooltip-title") || "")
                : (cell.getAttribute("data-tooltip-title-summary")  || cell.getAttribute("data-tooltip-title") || "");

            const items = (mode === "advanced")
                ? (cell.getAttribute("data-tooltip-items-advanced") || cell.getAttribute("data-tooltip-items") || "")
                : (cell.getAttribute("data-tooltip-items-summary")  || cell.getAttribute("data-tooltip-items") || "");

            // If empty, do nothing
            if (!title && !items) return;
            showTooltip(evt, title, items);
        });

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
    __overviewViewMode = mode;

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

def normalize_class(v) -> str:
    s = "" if v is None else str(v).strip()
    if s in ("High", "Low", "Avg"):
        return s
    return "Avg"

def classify_color(class_val):
    v = normalize_class(class_val)
    colors = COLOR_MAP_PY.get(v, COLOR_MAP_PY["Avg"])
    return (colors["bg"], colors["text"])

def arrow_for_class(cls: str) -> str:
    c = normalize_class(cls)
    if c == "High":
        return "↑"
    if c == "Low":
        return "↓"
    return "-"

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
    if pd.isna(x):
        return ""
    if col in DURATION_COLS:
        return f"{round(x):.0f}"
    return f"{x:.1f}"

def format_z(z):
    try:
        x = float(z)
    except Exception:
        return ""
    if pd.isna(x):
        return ""
    return f"{x:.2f}"

def unit_from_col(col: str) -> str:
    s = str(col)
    i1 = s.find("[")
    i2 = s.find("]")
    if i1 != -1 and i2 != -1 and i2 > i1:
        return s[i1+1:i2].strip()
    return ""

# ============================================================
# WORD DISPLAY (old words, unbolded, stacked)
# ============================================================
def word_for_duration(cls: str) -> str:
    c = normalize_class(cls)
    if c == "Low":
        return "Quicker"
    if c == "High":
        return "Slower"
    return "Normal"

def word_for_force(cls: str) -> str:
    c = normalize_class(cls)
    if c == "High":
        return "Stronger"
    if c == "Low":
        return "Weaker"
    return "Normal"

def word_for_depth(cls: str) -> str:
    c = normalize_class(cls)
    if c == "High":
        return "Deeper"
    if c == "Low":
        return "Shallower"
    return "Normal"

def label_to_word(lbl: str, cls: str) -> str:
    if lbl in ("PD", "BD"):
        return word_for_duration(cls)
    if lbl == "DEP":
        return word_for_depth(cls)
    if lbl in ("PF", "BF"):
        return word_for_force(cls)
    return "Normal"

def pretty_lbl(lbl: str) -> str:
    return {"PD":"Duration", "BD":"Duration", "DEP":"Depth", "PF":"Force", "BF":"Force"}.get(lbl, lbl)

def value_unit_z_text(colname: str, value, z) -> str:
    v_str = "" if pd.isna(value) else format_number(colname, value)
    if v_str == "":
        return ""
    unit = unit_from_col(colname)
    unit_str = f" {unit}" if unit else ""
    z_str = format_z(z)
    if z_str == "":
        return f"{v_str}{unit_str}"
    return f"{v_str}{unit_str} (Z: {z_str})"

def tooltip_label_for_component(lbl: str, colname: str, value, z) -> str:
    detail = value_unit_z_text(colname, value, z)
    if detail == "":
        return f"{lbl}: N/A"
    return f"{lbl}: {detail}"

# ============================================================
# EDIT 2: Advanced Abs/Gen cells show ONLY "Duration: Normal" etc.
#         Advanced Abs/Gen tooltip shows BD/PD/DEP/BF/PF values + Z
# ============================================================
def build_advanced_phase_cell_html_words_only(adv_items):
    lines = []
    for it in adv_items:
        lbl = it["lbl"]
        cls = normalize_class(it["cls"])
        word = label_to_word(lbl, cls)
        fg = classify_color(cls)[1]
        txt = f"{pretty_lbl(lbl)}: {word}"
        lines.append(f"<div class='adv-line' style='color:{fg};'>{html_escape(txt)}</div>")
    return "".join(lines)

def build_advanced_phase_tooltip_items_str(adv_items):
    parts = []
    for it in adv_items:
        lbl = it["lbl"]
        cls = normalize_class(it["cls"])
        col = it["col"]
        val = it["val"]
        z = it["z"]
        label = tooltip_label_for_component(lbl, col, val, z)
        parts.append(f"{label}|{cls}")
    return ";".join(parts)

# ============================================================
# LOGIC IMPLEMENTATION (unchanged)
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
    z_col = base_name + "_z"
    if z_col not in df.columns:
        for cand in [z_col + "_GEN", z_col + "_ABS", z_col + "_x", z_col + "_y"]:
            if cand in df.columns:
                df[z_col] = df[cand]
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
        return normalize_class(row.get(f"{base}_class", "Avg"))

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
# Phase component mapping
# ============================================================
def phase_component_columns(test_type, phase):
    if test_type == "CMJ":
        PD = "Concentric Duration [ms]"
        PF = "Concentric Mean Force / BM [N/kg]"
        BD = "Braking Phase Duration [ms]"
        DEP = "Countermovement Depth [cm]"
        BF = "Eccentric Mean Force / BM [N/kg]"
    elif test_type == "SLJ_L":
        PD = "Concentric Duration [ms] (L)"
        PF = "Concentric Mean Force / BM [N/kg] (L)"
        BD = "Braking Phase Duration [ms] (L)"
        DEP = "Countermovement Depth [cm] (L)"
        BF = "Eccentric Mean Force / BM [N/kg] (L)"
    else:
        PD = "Concentric Duration [ms] (R)"
        PF = "Concentric Mean Force / BM [N/kg] (R)"
        BD = "Braking Phase Duration [ms] (R)"
        DEP = "Countermovement Depth [cm] (R)"
        BF = "Eccentric Mean Force / BM [N/kg] (R)"

    if phase == "Generation":
        return [("PD", PD), ("DEP", DEP), ("PF", PF)]
    return [("BD", BD), ("DEP", DEP), ("BF", BF)]

# ============================================================
# Z-score fallback computation (per player, per test_type, per param)
# ============================================================
def z_fallback_for_player(df_all, player, value_col):
    if df_all is None or df_all.empty or value_col not in df_all.columns:
        return None
    sub = df_all[df_all[PLAYER_COL] == player].copy()
    if sub.empty:
        return None
    x = pd.to_numeric(sub[value_col], errors="coerce")
    mu = x.mean()
    sd = x.std(ddof=1)
    if pd.isna(sd) or sd == 0 or pd.isna(mu):
        return None
    return (x - mu) / sd

def compute_z_for_value(df_all, player, value_col, value):
    try:
        x_all = pd.to_numeric(df_all[df_all[PLAYER_COL] == player][value_col], errors="coerce")
        mu = x_all.mean()
        sd = x_all.std(ddof=1)
        x_cur = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(sd) or sd == 0 or pd.isna(mu) or pd.isna(x_cur):
            return None
        return (x_cur - mu) / sd
    except Exception:
        return None

def get_df_for_test(test_type):
    return cmj_daily if test_type == "CMJ" else sljL_daily if test_type == "SLJ_L" else sljR_daily

def get_latest_phase_components(player, test_type, phase):
    df = get_df_for_test(test_type)
    if df is None or df.empty:
        return ("", [], [])
    sub = df[df[PLAYER_COL] == player].copy()
    if sub.empty:
        return ("", [], [])
    sub = sub.sort_values(DATE_COL)
    last = sub.iloc[-1]
    date_val = last.get(DATE_COL, None)
    date_str = date_val.strftime("%Y-%m-%d") if isinstance(date_val, pd.Timestamp) else ""

    mapping = phase_component_columns(test_type, phase)

    tooltip_items_summary = []
    adv_items = []

    for lbl, col in mapping:
        cls = normalize_class(last.get(f"{col}_class", "Avg"))
        tooltip_items_summary.append((lbl, cls))

        val = last.get(col, None)

        z_val = last.get(f"{col}_z", None)
        if z_val is None or (isinstance(z_val, float) and pd.isna(z_val)) or str(z_val) == "nan":
            z_val = compute_z_for_value(df, player, col, val)

        adv_items.append({"lbl": lbl, "cls": cls, "col": col, "val": val, "z": z_val})

    return (date_str, tooltip_items_summary, adv_items)

# ============================================================
# TEAM OVERVIEW HTML HELPERS
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

    # ============================================================
    # EDIT 3: Explicit colgroup widths to keep cell sizes stable
    # ============================================================
    col_widths = {
        PLAYER_COL: "190px",
        "TTD": "120px",
        "LTD": "120px",
        "BW [KG]": "110px",
        "Jump Height (Imp-Mom) [cm]": "130px",
        "Jump Height (Imp-Mom) [cm] (L)": "130px",
        "Jump Height (Imp-Mom) [cm] (R)": "130px",
        "CMJ_ABS_OVR": "120px",
        "CMJ_GEN_OVR": "120px",
        "SLJ_L_ABS_OVR": "120px",
        "SLJ_L_GEN_OVR": "120px",
        "SLJ_R_ABS_OVR": "120px",
        "SLJ_R_GEN_OVR": "120px",
    }
    colgroup = "<colgroup>" + "".join([f"<col style='width:{col_widths.get(c,'120px')}'>" for c in cols]) + "</colgroup>"

    header_cells = "".join(f"<th>{display_labels.get(c, c)}</th>" for c in cols)

    html_rows = []
    for _, row in df.iterrows():
        player = row.get(PLAYER_COL, "")
        player_filename = safe_player_filename(player)

        # ============================================================
        # ONLY CHANGE: BW + JH class logic for TEAM OVERVIEW PAGE
        # - Use latest DAILY class per athlete (per-test) for coloring
        # - If daily class missing, fall back to whatever is in the overview row
        # ============================================================
        bw_cls_row = row.get("BW [KG]_class", None)
        cmj_jh_cls_row = row.get("Jump Height (Imp-Mom) [cm]_class", None)
        sljL_jh_cls_row = row.get("Jump Height (Imp-Mom) [cm] (L)_class", None)
        sljR_jh_cls_row = row.get("Jump Height (Imp-Mom) [cm] (R)_class", None)

        bw_cls = get_latest_param_class(player, "CMJ", "BW [KG]")
        cmj_jh_cls = get_latest_param_class(player, "CMJ", "Jump Height (Imp-Mom) [cm]")
        sljL_jh_cls = get_latest_param_class(player, "SLJ_L", "Jump Height (Imp-Mom) [cm] (L)")
        sljR_jh_cls = get_latest_param_class(player, "SLJ_R", "Jump Height (Imp-Mom) [cm] (R)")

        if bw_cls not in ["High", "Low", "Avg"]:
            bw_cls = bw_cls_row
        if cmj_jh_cls not in ["High", "Low", "Avg"]:
            cmj_jh_cls = cmj_jh_cls_row
        if sljL_jh_cls not in ["High", "Low", "Avg"]:
            sljL_jh_cls = sljL_jh_cls_row
        if sljR_jh_cls not in ["High", "Low", "Avg"]:
            sljR_jh_cls = sljR_jh_cls_row

        mean_bw_cmj   = get_param_mean(player, "CMJ",   "BW [KG]")
        mean_jh_cmj   = get_param_mean(player, "CMJ",   "Jump Height (Imp-Mom) [cm]")
        mean_jh_sljL  = get_param_mean(player, "SLJ_L", "Jump Height (Imp-Mom) [cm] (L)")
        mean_jh_sljR  = get_param_mean(player, "SLJ_R", "Jump Height (Imp-Mom) [cm] (R)")

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

            # Weight + Jump Heights: always colored and tooltip mean stays same in both views
            if col == "BW [KG]":
                bg, fg = classify_color(bw_cls)
                title = (f"CMJ Body Weight mean: {mean_bw_cmj:.1f} kg"
                         if mean_bw_cmj is not None else "CMJ Body Weight mean: N/A")
                row_tds.append(
                    f'<td class="metric-cell cell-tight" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">'
                    f'{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm]":
                bg, fg = classify_color(cmj_jh_cls)
                title = (f"CMJ Jump Height mean: {mean_jh_cmj:.1f} cm"
                         if mean_jh_cmj is not None else "CMJ Jump Height mean: N/A")
                row_tds.append(
                    f'<td class="metric-cell cell-tight" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">'
                    f'{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm] (L)":
                bg, fg = classify_color(sljL_jh_cls)
                title = (f"SLJ-L Jump Height mean: {mean_jh_sljL:.1f} cm"
                         if mean_jh_sljL is not None else "SLJ-L Jump Height mean: N/A")
                row_tds.append(
                    f'<td class="metric-cell cell-tight" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">'
                    f'{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm] (R)":
                bg, fg = classify_color(sljR_jh_cls)
                title = (f"SLJ-R Jump Height mean: {mean_jh_sljR:.1f} cm"
                         if mean_jh_sljR is not None else "SLJ-R Jump Height mean: N/A")
                row_tds.append(
                    f'<td class="metric-cell cell-tight" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">'
                    f'{html_escape(val_str)}</td>'
                )
                continue

            # Abs/Gen columns: Summary tooltip stays your current chips; Advanced tooltip becomes value+z chips.
            if col in metric_phase_map:
                test_type, phase = metric_phase_map[col]
                overall_cls = normalize_class(val_str)
                bg, fg = classify_color(overall_cls)

                date_str, tooltip_items_summary, adv_items = get_latest_phase_components(player, test_type, phase)

                items_str_summary = ";".join(f"{lbl}|{cls}" for (lbl, cls) in tooltip_items_summary if lbl and cls)
                tooltip_title_summary = f"{test_type} {phase} ({date_str})"

                tooltip_title_advanced = f"{test_type} {phase} details ({date_str})"
                items_str_advanced = build_advanced_phase_tooltip_items_str(adv_items)

                summary_disp = arrow_for_class(overall_cls)

                # Advanced cell now shows words only
                advanced_cell_html = build_advanced_phase_cell_html_words_only(adv_items)

                row_tds.append(
                    f'<td class="metric-cell phase-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title-summary="{html_escape(tooltip_title_summary)}" '
                    f'data-tooltip-items-summary="{html_escape(items_str_summary)}" '
                    f'data-tooltip-title-advanced="{html_escape(tooltip_title_advanced)}" '
                    f'data-tooltip-items-advanced="{html_escape(items_str_advanced)}">'
                    f'  <div class="view-summary" style="font-weight:900;font-size:16px;line-height:1;">{html_escape(summary_disp)}</div>'
                    f'  <div class="view-advanced" style="display:none;">{advanced_cell_html}</div>'
                    f'</td>'
                )
                continue

            row_tds.append(f"<td class='cell-tight'>{html_escape(val_str)}</td>")

        html_rows.append("<tr>" + "".join(row_tds) + "</tr>")

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Team CMJ / SLJ Overview</title>
<style>
:root {{
    --primary-200:#CE0E2D;
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

.table-wrap {{
    width: 100%;
    overflow-x: auto; /* keep sizing consistent; allow horizontal scroll if needed */
    border-radius: 10px;
}}

table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed; /* stable columns */
    font-size: 12px;
    background: rgba(255,255,255,0.06);
}}

th, td {{
    border: 1px solid rgba(255,255,255,0.18);
    padding: 4px 6px;
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.cell-tight {{
    white-space: nowrap; /* prevents random wrap differences across screens */
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
    white-space: nowrap;
}}

a {{
    color: inherit;
    text-decoration: none;
    font-weight: 600;
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

.view-advanced {{
    font-weight: 400; /* NOT bold */
    font-size: 11px;
    line-height: 1.2;
    text-align: left;
    white-space: normal; /* allow stacked words in phase cells */
}}
.view-advanced .adv-line {{
    margin: 2px 0;
    font-weight: 400; /* NOT bold */
}}
.phase-cell {{ padding: 6px 6px; }}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <h1>CMJ & SLJ Team Overview</h1>
    <p style="margin:0; color: var(--text-200);">
      Hover over Absorption and Generation cells to see classifications.
      Click a player's name to view their history.
      Use the view toggle to switch between summary and advanced views.
    </p>
  </div>

  <div class="view-toggle" title="Switch between Summary and Advanced views">
    <span class="label">View:</span>
    <button id="btn-view-summary" type="button">Summary</button>
    <button id="btn-view-advanced" type="button">Advanced</button>
  </div>
</div>

<div class="table-wrap">
  <table class="sortable-table">
      {colgroup}
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{"".join(html_rows)}</tbody>
  </table>
</div>

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

        # ============================================================
        # EDIT 4: colgroup widths for player tables (stable sizing)
        # ============================================================
        colgroup = "<colgroup>"
        for c in cols:
            if c == DATE_COL:
                colgroup += "<col style='width:110px'>"
            elif c in (abs_col, gen_col):
                colgroup += "<col style='width:170px'>"
            else:
                colgroup += "<col style='width:150px'>"
        colgroup += "</colgroup>"

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
                    tds.append(f"<td class='cell-tight'>{html_escape(date_str)}</td>")
                    continue

                # Abs/Gen columns: Summary tooltip stays chips; Advanced tooltip becomes value+z chips.
                if c in [gen_col, abs_col]:
                    cls_val = normalize_class(v)
                    bg, fg = classify_color(cls_val)
                    phase = "Generation" if c == gen_col else "Absorption"

                    mapping = phase_component_columns(test_type, phase)

                    tooltip_items_summary = [(lbl, normalize_class(r.get(f"{colname}_class", "Avg"))) for (lbl, colname) in mapping]
                    items_str_summary = ";".join(f"{lbl}|{cls}" for (lbl, cls) in tooltip_items_summary if lbl and cls)
                    tooltip_title_summary = f"{test_type} {phase} ({date_str})"

                    adv_items = []
                    for lbl, colname in mapping:
                        comp_cls = normalize_class(r.get(f"{colname}_class", "Avg"))
                        comp_val = r.get(colname, None)

                        comp_z = r.get(f"{colname}_z", None)
                        if comp_z is None or (isinstance(comp_z, float) and pd.isna(comp_z)) or str(comp_z) == "nan":
                            comp_z = compute_z_for_value(df_daily, player, colname, comp_val)

                        adv_items.append({"lbl": lbl, "cls": comp_cls, "col": colname, "val": comp_val, "z": comp_z})

                    tooltip_title_advanced = f"{test_type} {phase} details ({date_str})"
                    items_str_advanced = build_advanced_phase_tooltip_items_str(adv_items)

                    summary_disp = arrow_for_class(cls_val)

                    # Advanced cell shows words ONLY (no values)
                    advanced_cell_html = build_advanced_phase_cell_html_words_only(adv_items)

                    tds.append(
                        f'<td class="metric-cell phase-cell" style="background-color:{bg};color:{fg};" '
                        f'data-tooltip-title-summary="{html_escape(tooltip_title_summary)}" '
                        f'data-tooltip-items-summary="{html_escape(items_str_summary)}" '
                        f'data-tooltip-title-advanced="{html_escape(tooltip_title_advanced)}" '
                        f'data-tooltip-items-advanced="{html_escape(items_str_advanced)}">'
                        f'  <div class="view-summary" style="font-weight:900;font-size:16px;line-height:1;">{html_escape(summary_disp)}</div>'
                        f'  <div class="view-advanced" style="display:none;">{advanced_cell_html}</div>'
                        f'</td>'
                    )
                    continue

                # Numeric parameter columns: mean tooltip stays same in both views
                if c in numeric_cols:
                    cls_val = normalize_class(r.get(value_col_map[c]["class_col"], "Avg"))
                    bg, fg = classify_color(cls_val)
                    tt_title = tooltip_for_avg_prev(r, c, value_col_map[c]["label"])

                    v_summary = "" if pd.isna(v) else format_number(c, v)

                    z_val = r.get(f"{c}_z", None)
                    if z_val is None or (isinstance(z_val, float) and pd.isna(z_val)) or str(z_val) == "nan":
                        z_val = compute_z_for_value(df_daily, player, c, v)
                    z_str = format_z(z_val)

                    v_adv = v_summary if z_str == "" or v_summary == "" else f"{v_summary} (Z: {z_str})"

                    tds.append(
                        f'<td class="metric-cell cell-tight" style="background-color:{bg};color:{fg};" '
                        f'data-tooltip-title="{html_escape(tt_title)}" data-tooltip-items="">'
                        f'  <span class="view-summary">{html_escape(v_summary)}</span>'
                        f'  <span class="view-advanced" style="display:none;">{html_escape(v_adv)}</span>'
                        f'</td>'
                    )
                    continue

                tds.append(f"<td class='cell-tight'>{html_escape(v)}</td>")

            body_rows.append("<tr>" + "".join(tds) + "</tr>")

        return f"""
<h2>{html_escape(title)}</h2>
<div class="table-wrap">
<table class="sortable-table paginated-table">
    {colgroup}
    <thead><tr>{"".join(header_cells)}</tr></thead>
    <tbody>{"".join(body_rows)}</tbody>
</table>
</div>
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
    --primary-200:#CE0E2D;
    --text-100:#FFFFFF;
    --text-200:#e0e0e0;
    --bg-100:#0A2240;
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
    font-weight: 600;
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
    font-weight: 700;
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

.table-wrap {{
    width: 100%;
    overflow-x: auto; /* stable sizing + scroll */
    border-radius: 10px;
}}

table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed; /* stable columns */
    font-size: 12px;
    margin-bottom: 20px;
    background: rgba(255,255,255,0.06);
}}

th, td {{
    border: 1px solid rgba(255,255,255,0.18);
    padding: 4px 6px;
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.cell-tight {{ white-space: nowrap; }}

th {{
    background-color: var(--bg-300);
    color: var(--text-100);
}}

tbody tr:nth-child(even) {{ background-color: rgba(255,255,255,0.06); }}
tbody tr:nth-child(odd)  {{ background-color: rgba(255,255,255,0.03); }}

.view-advanced {{
    font-weight: 400; /* NOT bold */
    font-size: 11px;
    line-height: 1.2;
    text-align: left;
    white-space: normal; /* stacked words for Abs/Gen */
}}
.view-advanced .adv-line {{
    margin: 2px 0;
    font-weight: 400; /* NOT bold */
}}
.phase-cell {{ padding: 6px 6px; }}
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
    <p style="margin:0; color: var(--text-200);">
      Hover over Absorption and Generation cells to see classifications.
      Click a player's name to view their history.
      Use the view toggle to switch between summary and advanced views.
    </p>
  </div>
  <div class="view-toggle" title="Switch between Summary and Advanced views">
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
