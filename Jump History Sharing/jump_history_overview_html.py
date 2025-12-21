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
# 1) BUILD THE TEAM OVERVIEW CSV + PDF
# ============================================================
cmj = pd.read_csv(CMJ_TEAM_CSV)
sljL = pd.read_csv(SLJ_L_TEAM_CSV)
sljR = pd.read_csv(SLJ_R_TEAM_CSV)

# Clean column names
for df in [cmj, sljL, sljR]:
    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.replace("\xa0", " ", regex=False)
        .str.strip()
    )

# ---- CMJ subset
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

cmj_sub = cmj_sub.rename(
    columns={
        "Absorption_Class": "CMJ_ABS_OVR",
        "Generation_Class": "CMJ_GEN_OVR",
    }
)

# ---- SLJ Left subset
sljL_cols = [PLAYER_COL, "Absorption_Class_L", "Generation_Class_L"]
jhL_col = "Jump Height (Imp-Mom) [cm] (L)"
if jhL_col in sljL.columns:
    sljL_cols.insert(1, jhL_col)

sljL_sub = sljL[sljL_cols].copy()
sljL_sub = sljL_sub.rename(
    columns={
        "Absorption_Class_L": "SLJ_L_ABS_OVR",
        "Generation_Class_L": "SLJ_L_GEN_OVR",
    }
)

# ---- SLJ Right subset
sljR_cols = [PLAYER_COL, "Absorption_Class_R", "Generation_Class_R"]
jhR_col = "Jump Height (Imp-Mom) [cm] (R)"
if jhR_col in sljR.columns:
    sljR_cols.insert(1, jhR_col)

sljR_sub = sljR[sljR_cols].copy()
sljR_sub = sljR_sub.rename(
    columns={
        "Absorption_Class_R": "SLJ_R_ABS_OVR",
        "Generation_Class_R": "SLJ_R_GEN_OVR",
    }
)

# ---- merge all
summary = (
    cmj_sub
    .merge(sljL_sub, on=PLAYER_COL, how="left")
    .merge(sljR_sub, on=PLAYER_COL, how="left")
)

# Sort by last testing date (most recent on top)
if "LTD" in summary.columns:
    summary["_LTD_dt"] = pd.to_datetime(summary["LTD"], errors="coerce")
    summary = summary.sort_values("_LTD_dt", ascending=False).drop(columns=["_LTD_dt"])
else:
    summary = summary.sort_values(PLAYER_COL)

# ---- Team-level z-score classes (BW/JH)
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

# ---- PDF styling (unchanged behavior)
COLOR_MAP = {
    "High": {"face": "#FF7276", "text": "black"},
    "Low":  {"face": "#87CEEB", "text": "#305CDE"},
    "Avg":  {"face": "#D3D3D3", "text": "black"},
}

DISPLAY_LABELS = {
    PLAYER_COL: "PLAYER",
    "TTD": "Total\nTesting Days",
    "LTD": "Last\nTesting Date",
    "BW [KG]": "Weight\n(kg)",
    "Jump Height (Imp-Mom) [cm]": "CMJ\nJump Height",
    "Jump Height (Imp-Mom) [cm] (L)": "SLJ-L\nJump Height",
    "Jump Height (Imp-Mom) [cm] (R)": "SLJ-R\nJump Height",
    "CMJ_ABS_OVR":   "CMJ\nAbsorption",
    "CMJ_GEN_OVR":   "CMJ\nGeneration",
    "SLJ_L_ABS_OVR": "SLJ-L\nAbsorption",
    "SLJ_L_GEN_OVR": "SLJ-L\nGeneration",
    "SLJ_R_ABS_OVR": "SLJ-R\nAbsorption",
    "SLJ_R_GEN_OVR": "SLJ-R\nGeneration",
}

def display_name(col):
    return DISPLAY_LABELS.get(col, col)

def format_value(val):
    if pd.isna(val):
        return ""
    return str(val)

def class_to_arrow(text):
    if text == "High":
        return "↑"
    if text == "Low":
        return "↓"
    return text

cols = [
    PLAYER_COL,
    "TTD",
    "LTD",
    "BW [KG]",
    "Jump Height (Imp-Mom) [cm]",
    "Jump Height (Imp-Mom) [cm] (L)",
    "Jump Height (Imp-Mom) [cm] (R)",
    "CMJ_ABS_OVR", "CMJ_GEN_OVR",
    "SLJ_L_ABS_OVR", "SLJ_L_GEN_OVR",
    "SLJ_R_ABS_OVR", "SLJ_R_GEN_OVR",
]
cols = [c for c in cols if c in summary.columns]
header_labels = [display_name(c) for c in cols]

OVR_CLASS_COLUMNS = {
    "CMJ_ABS_OVR",
    "CMJ_GEN_OVR",
    "SLJ_L_ABS_OVR",
    "SLJ_L_GEN_OVR",
    "SLJ_R_ABS_OVR",
    "SLJ_R_GEN_OVR",
}

data_rows = []
for _, row in summary.iterrows():
    row_vals = []
    for c in cols:
        raw = row.get(c, "")
        disp = format_value(raw)
        if c in OVR_CLASS_COLUMNS:
            disp = class_to_arrow(disp)
        row_vals.append(disp)
    data_rows.append(row_vals)

n_rows = len(data_rows)
n_cols = len(cols)

fig_width = max(11, n_cols * 1.4)
fig_height = max(5, n_rows * 0.45 + 2)

fig, ax = plt.subplots(figsize=(fig_width, fig_height))
ax.axis("off")

table = ax.table(
    cellText=data_rows,
    colLabels=header_labels,
    loc="center"
)

table.auto_set_font_size(False)
table.set_fontsize(8)
table.scale(1.2, 1.3)

try:
    table.auto_set_column_width(col=list(range(n_cols)))
except Exception:
    pass

for (r, c), cell in table.get_celld().items():
    if r == 0:
        cell.set_facecolor("black")
        cell.get_text().set_color("white")
        cell.get_text().set_fontweight("bold")

CLASS_COL_MAP = {
    "BW [KG]": "BW [KG]_class",
    "Jump Height (Imp-Mom) [cm]": "Jump Height (Imp-Mom) [cm]_class",
    "Jump Height (Imp-Mom) [cm] (L)": "Jump Height (Imp-Mom) [cm] (L)_class",
    "Jump Height (Imp-Mom) [cm] (R)": "Jump Height (Imp-Mom) [cm] (R)_class",
    "CMJ_ABS_OVR": "CMJ_ABS_OVR",
    "CMJ_GEN_OVR": "CMJ_GEN_OVR",
    "SLJ_L_ABS_OVR": "SLJ_L_ABS_OVR",
    "SLJ_L_GEN_OVR": "SLJ_L_GEN_OVR",
    "SLJ_R_ABS_OVR": "SLJ_R_ABS_OVR",
    "SLJ_R_GEN_OVR": "SLJ_R_GEN_OVR",
}

col_idx_to_name = {idx: col for idx, col in enumerate(cols)}

for r_idx, (_, row) in enumerate(summary.iterrows(), start=1):
    for c_idx in range(len(cols)):
        col = col_idx_to_name[c_idx]
        if col not in CLASS_COL_MAP:
            continue
        class_col = CLASS_COL_MAP[col]
        if class_col not in summary.columns:
            continue

        cls = row.get(class_col, "Avg")
        if cls not in COLOR_MAP:
            cls = "Avg"

        cell = table[r_idx, c_idx]
        colors = COLOR_MAP[cls]
        cell.set_facecolor(colors["face"])
        cell.get_text().set_color(colors["text"])

ax.set_title("CMJ & SLJ Classification Overview", fontsize=20, pad=20)
plt.tight_layout(rect=[0, 0, 1, 1])

with PdfPages(OUTPUT_SUMMARY_PDF) as pdf:
    pdf.savefig(fig)
    plt.close(fig)

print("Saved unified team overview PDF to:", OUTPUT_SUMMARY_PDF)

# ============================================================
# 2) HTML GENERATION (Team Overview + Player Pages)
#   Updates you requested:
#   - Team overview "Name" cell shows (image + name)
#   - Player page header top-right shows (player image + name) instead of PKMN logo
#   - Paths consolidated above
# ============================================================

# ----------------- Shared JS (unchanged) -----------------
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
    if (a < b) return asc ? -0.5 : 0.5; // small bias for stable-ish behavior
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

    if (x + w + margin > window.innerWidth) {
        x = evt.clientX - w - padding;
    }
    if (y + h + margin > window.innerHeight) {
        y = evt.clientY - h - padding;
    }

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

// ---------- Pagination for paginated tables ----------
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
            if (currentPage > 0) {
                currentPage--;
                renderPage();
            }
        });

        nextBtn.addEventListener("click", () => {
            currentPage++;
            renderPage();
        });

        renderPage();
    });
}

document.addEventListener("DOMContentLoaded", () => {
    makeTablesSortable();
    attachMetricTooltips();
    initPagination();
});
"""

# ----------------- Python helpers -----------------
COLOR_MAP_PY = {
    "High": {"bg": "#FF7276", "text": "#840000"},
    "Low":  {"bg": "#87CEEB", "text": "#305CDE"},
    "Avg":  {"bg": "#D3D3D3", "text": "black"},
}

def classify_color(class_val):
    v = str(class_val)
    colors = COLOR_MAP_PY.get(v, COLOR_MAP_PY["Avg"])
    return (colors["bg"], colors["text"])

def class_to_arrow_text(text):
    t = str(text)
    if t == "High":
        return "↑"
    if t == "Low":
        return "↓"
    if t == "Avg":
        return "-"
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

# Player headshot (relative path). Uses URL-encoding for spaces, etc.
def player_headshot_rel(player_name: str) -> str:
    # Your files are literally "Name.png"
    # HTML needs URL-safe paths (spaces -> %20)
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
    return pd.merge(
        gen_df, abs_df,
        on=[PLAYER_COL, DATE_COL],
        how="outer",
        suffixes=("_GEN", "_ABS")
    )

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
    else:  # SLJ_R
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

# ============================================================
# MEANS + CLASSES HELPERS (same logic)
# ============================================================
def get_param_mean(player, test_type, param_col):
    if test_type == "CMJ":
        df = cmj_daily
    elif test_type == "SLJ_L":
        df = sljL_daily
    else:
        df = sljR_daily

    if df is None or df.empty or param_col not in df.columns:
        return None
    sub = df[df[PLAYER_COL] == player]
    if sub.empty:
        return None
    vals = pd.to_numeric(sub[param_col], errors="coerce")
    m = vals.mean()
    if pd.isna(m):
        return None
    return m

def get_latest_param_class(player, test_type, param_col):
    if test_type == "CMJ":
        df = cmj_daily
    elif test_type == "SLJ_L":
        df = sljL_daily
    else:
        df = sljR_daily

    if df is None or df.empty or param_col not in df.columns:
        return None
    sub = df[df[PLAYER_COL] == player].copy()
    if sub.empty:
        return None
    sub = sub.sort_values(DATE_COL)
    last = sub.iloc[-1]
    cls_col = f"{param_col}_class"
    return last.get(cls_col, None)

def get_latest_bw_jh_class(player):
    if cmj_daily.empty:
        return (None, None)
    sub = cmj_daily[cmj_daily[PLAYER_COL] == player].copy()
    if sub.empty:
        return (None, None)
    sub = sub.sort_values(DATE_COL)
    last = sub.iloc[-1]
    bw_cls = last.get("BW [KG]_class", None)
    jh_cls = last.get("Jump Height (Imp-Mom) [cm]_class", None)
    return (bw_cls, jh_cls)

def get_latest_phase_components(player, test_type, phase):
    if test_type == "CMJ":
        df = cmj_daily
        dur_col = "Concentric Duration [ms]"
        force_col = "Concentric Mean Force / BM [N/kg]"
        bd_col = "Braking Phase Duration [ms]"
        dep_col = "Countermovement Depth [cm]"
        bf_col = "Eccentric Mean Force / BM [N/kg]"
    elif test_type == "SLJ_L":
        df = sljL_daily
        dur_col = "Concentric Duration [ms] (L)"
        force_col = "Concentric Mean Force / BM [N/kg] (L)"
        bd_col = "Braking Phase Duration [ms] (L)"
        dep_col = "Countermovement Depth [cm] (L)"
        bf_col = "Eccentric Mean Force / BM [N/kg] (L)"
    elif test_type == "SLJ_R":
        df = sljR_daily
        dur_col = "Concentric Duration [ms] (R)"
        force_col = "Concentric Mean Force / BM [N/kg] (R)"
        bd_col = "Braking Phase Duration [ms] (R)"
        dep_col = "Countermovement Depth [cm] (R)"
        bf_col = "Eccentric Mean Force / BM [N/kg] (R)"
    else:
        return ("", [])

    if df is None or df.empty:
        return ("", [])

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
        return (date_str, [("PD", get_class(dur_col)), ("PF", get_class(force_col))])
    return (date_str, [("BD", get_class(bd_col)), ("DEP", get_class(dep_col)), ("BF", get_class(bf_col))])

# ============================================================
# TEAM OVERVIEW HTML (UPDATED: avatar next to name)
# ============================================================
def build_team_overview_html(df: pd.DataFrame, out_path: str):
    cols = [
        PLAYER_COL,
        "TTD",
        "LTD",
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
                # UPDATED: image + name in sticky name cell.
                # onerror hides image if missing.
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
                title = f"CMJ Body Weight - hist mean: {mean_bw_cmj:.1f} kg" if mean_bw_cmj is not None else "CMJ Body Weight - no historical mean"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm]":
                bg, fg = classify_color(row_cmj_jh_cls)
                title = f"CMJ Jump Height - hist mean: {mean_jh_cmj:.1f} cm" if mean_jh_cmj is not None else "CMJ Jump Height - no historical mean"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm] (L)":
                bg, fg = classify_color(row_sljL_jh_cls)
                title = f"SLJ-L Jump Height - hist mean: {mean_jh_sljL:.1f} cm" if mean_jh_sljL is not None else "SLJ-L Jump Height - no historical mean"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">{html_escape(val_str)}</td>'
                )
                continue

            if col == "Jump Height (Imp-Mom) [cm] (R)":
                bg, fg = classify_color(row_sljR_jh_cls)
                title = f"SLJ-R Jump Height - hist mean: {mean_jh_sljR:.1f} cm" if mean_jh_sljR is not None else "SLJ-R Jump Height - no historical mean"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(title)}" data-tooltip-items="">{html_escape(val_str)}</td>'
                )
                continue

            if col in metric_phase_map:
                test_type, phase = metric_phase_map[col]
                bg, fg = classify_color(val_str)
                display_val = class_to_arrow_text(val_str)
                date_str, items = get_latest_phase_components(player, test_type, phase)
                items_str = ";".join(f"{lbl}|{cls}" for (lbl, cls) in items if lbl and cls)
                tooltip_title = f"{test_type} {phase} (latest: {date_str})"
                row_tds.append(
                    f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                    f'data-tooltip-title="{html_escape(tooltip_title)}" data-tooltip-items="{html_escape(items_str)}">{html_escape(display_val)}</td>'
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
body {{
    font-family: Arial, sans-serif;
    margin: 20px;
}}

.page-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
}}

.header-left h1 {{
    margin: 0;
    line-height: 1.1;
}}

table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
    font-size: 12px;
}}
th, td {{
    border: 1px solid #ccc;
    padding: 4px 6px;
    text-align: center;
    word-wrap: break-word;
}}
th {{
    background-color: black;
    color: white;
    position: sticky;
    top: 0;
    z-index: 2;
}}
.sticky-name {{
    position: sticky;
    left: 0;
    background-color: #f9f9f9;
    z-index: 1;
    text-align: left;
}}
a {{
    color: inherit;
    text-decoration: none;
    font-weight: bold;
}}
a:hover {{
    text-decoration: underline;
}}
tbody tr:nth-child(even) {{
    background-color: #f5f5f5;
}}

/* NEW: avatar in player name cell */
.player-link {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
}}
.player-avatar {{
    width: 22px;
    height: 22px;
    border-radius: 50%;
    object-fit: cover;
    border: 1px solid #ccc;
    flex: 0 0 auto;
}}
.player-name-text {{
    display: inline-block;
}}
</style>
</head>
<body>

<div class="page-header">
    <div class="header-left">
        <h1>CMJ & SLJ Team Overview</h1>
    </div>
</div>

<p>Hover over CMJ/SLJ Absorption & Generation cells to see parameter classes. Hover over Weight & Jump Height cells to see that player's historical mean. Click a player's name for their jump history.</p>

<table class="sortable-table">
    <thead>
        <tr>{header_cells}</tr>
    </thead>
    <tbody>
        {"".join(html_rows)}
    </tbody>
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
# PLAYER HISTORY HTML (UPDATED: top-right player name + headshot)
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
            dur_col = "Concentric Duration [ms]"
            force_col = "Concentric Mean Force / BM [N/kg]"
            bd_col = "Braking Phase Duration [ms]"
            dep_col = "Countermovement Depth [cm]"
            bf_col = "Eccentric Mean Force / BM [N/kg]"
        elif test_type == "SLJ_L":
            dur_col = "Concentric Duration [ms] (L)"
            force_col = "Concentric Mean Force / BM [N/kg] (L)"
            bd_col = "Braking Phase Duration [ms] (L)"
            dep_col = "Countermovement Depth [cm] (L)"
            bf_col = "Eccentric Mean Force / BM [N/kg] (L)"
        else:  # SLJ_R
            dur_col = "Concentric Duration [ms] (R)"
            force_col = "Concentric Mean Force / BM [N/kg] (R)"
            bd_col = "Braking Phase Duration [ms] (R)"
            dep_col = "Countermovement Depth [cm] (R)"
            bf_col = "Eccentric Mean Force / BM [N/kg] (R)"

        if phase == "Generation":
            items = [("PD", row.get(f"{dur_col}_class", "")), ("PF", row.get(f"{force_col}_class", ""))]
        else:
            items = [("BD", row.get(f"{bd_col}_class", "")), ("DEP", row.get(f"{dep_col}_class", "")), ("BF", row.get(f"{bf_col}_class", ""))]

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
            return f"{label} baseline mean: N/A (first test)"
        try:
            avg_str = format_number(value_col, avg_val)
        except Exception:
            avg_str = str(avg_val)
        return f"{label} baseline mean: {avg_str}"

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
        else:  # SLJ_R
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
        cols = [DATE_COL, abs_col, gen_col]

        value_col_map = {spec["value_col"]: spec for spec in param_specs}
        cols.extend([spec["value_col"] for spec in param_specs])

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

        numeric_cols = set(value_col_map.keys())

        body_rows = []
        for _, r in sub.iterrows():
            tds = []
            date_val = r.get(DATE_COL, None)
            date_str = date_val.strftime("%Y-%m-%d") if isinstance(date_val, pd.Timestamp) else ""

            for c in cols:
                v = r.get(c, "")

                if c == DATE_COL:
                    tds.append(f"<td>{html_escape(date_str)}</td>")
                    continue

                if c == gen_col or c == abs_col:
                    cls_val = "" if pd.isna(v) else str(v)
                    bg, fg = classify_color(cls_val)
                    disp = class_to_arrow_text(cls_val)

                    phase = "Generation" if c == gen_col else "Absorption"
                    items = get_row_phase_items(r, test_type, phase)
                    items_str = ";".join(f"{lbl}|{cls}" for (lbl, cls) in items if lbl and cls)
                    tooltip_title = f"{test_type} {phase} ({date_str})"

                    tds.append(
                        f'<td class="metric-cell" style="background-color:{bg};color:{fg};" '
                        f'data-tooltip-title="{html_escape(tooltip_title)}" '
                        f'data-tooltip-items="{html_escape(items_str)}">{html_escape(disp)}</td>'
                    )
                    continue

                if c in numeric_cols:
                    v_str = "" if pd.isna(v) else format_number(c, v)
                    class_col = value_col_map[c]["class_col"]
                    label = value_col_map[c]["label"]

                    cls_val = r.get(class_col, "Avg")
                    bg, fg = classify_color(cls_val)
                    tt_title = tooltip_for_avg_prev(r, c, label)

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

    # UPDATED: top-right player identity (name + headshot)
    player_img = player_headshot_rel(player)

    full_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html_escape(player)} - Jump History</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 20px;
}}

.page-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
}}

.header-left h1 {{
    margin: 0;
    line-height: 1.1;
}}

.back-link {{
    display: inline-block;
    margin-top: 8px;
    color: #0055aa;
    text-decoration: none;
}}
.back-link:hover {{
    text-decoration: underline;
}}

/* NEW: top-right player identity */
.player-identity {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 0 0 auto;
}}
.player-identity img {{
    width: 48px;
    height: 48px;
    border-radius: 50%;
    object-fit: cover;
    border: 1px solid #ccc;
}}
.player-identity .player-identity-name {{
    font-weight: 800;
    font-size: 16px;
    white-space: nowrap;
}}

h2 {{
    margin-top: 20px;
}}

.table-pagination-controls {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
    font-size: 12px;
}}
.table-pagination-controls select {{
    font-size: 12px;
}}
.table-pagination-controls button {{
    font-size: 11px;
    padding: 2px 6px;
}}

table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: auto;
    font-size: 12px;
    margin-bottom: 20px;
}}
th, td {{
    border: 1px solid #ccc;
    padding: 4px 6px;
    text-align: center;
}}
th {{
    background-color: black;
    color: white;
}}
a {{
    color: #0055aa;
    text-decoration: none;
}}
a:hover {{
    text-decoration: underline;
}}
</style>
</head>
<body>

<div class="page-header">
    <div class="header-left">
        <h1>Jump History</h1>
        <a class="back-link" href="index.html">&larr; Back to Team Overview</a>
    </div>

    <div class="player-identity">
        <img src="{player_img}" alt="{html_escape(player)}"
             onerror="this.style.display='none';" />
        <div class="player-identity-name">{html_escape(player)}</div>
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
    # Team overview
    index_path = os.path.join(ROOT_OVERVW, "index.html")
    build_team_overview_html(team_df, index_path)

    # Player pages
    players = team_df[PLAYER_COL].dropna().unique()
    for p in players:
        fname = safe_player_filename(p)
        out_path = os.path.join(ROOT_OVERVW, fname)
        build_player_history_html(p, out_path)
