import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# -------------------------------------------------------------
# FILE PATHS
# -------------------------------------------------------------
ROOT = r"C:\Example Data\VALD Jump Exports\Historical CMJ"
INPUT_FILE       = os.path.join(ROOT, "raw_VALD_cmj.csv")
OUTPUT_GEN_CSV   = os.path.join(ROOT, "Generation_Daily_Classes.csv")
OUTPUT_ABS_CSV   = os.path.join(ROOT, "Absorption_Daily_Classes.csv")
OUTPUT_TEAM_CSV  = os.path.join(ROOT, "Team_CMJ_Snapshot.csv")
PDF_OUTPUT_DIR   = os.path.join(ROOT, "Player_PDFs")
TEAM_PDF_PATH    = os.path.join(ROOT, "CMJ_Team_Overview.pdf")

PLAYER_COL = "Name"
DATE_COL   = "Date"

# -------------------------------------------------------------
# 1. LOAD & CLEAN HEADERS
# -------------------------------------------------------------
df = pd.read_csv(INPUT_FILE)

df.columns = (
    df.columns.astype(str)
      .str.replace('\ufeff', '', regex=False)   # BOM
      .str.replace('\xa0', ' ', regex=False)    # non-breaking space
      .str.strip()
)

# -------------------------------------------------------------
# 2. PREP DATE + SORT
# -------------------------------------------------------------
if PLAYER_COL not in df.columns or DATE_COL not in df.columns:
    raise SystemExit(
        f"'{PLAYER_COL}' or '{DATE_COL}' column missing.\n"
        f"Columns: {df.columns.tolist()}"
    )

df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
df = df.dropna(subset=[PLAYER_COL, DATE_COL]).sort_values([PLAYER_COL, DATE_COL])

# -------------------------------------------------------------
# 3. DEFINE PARAMETER SETS
#   NOTE: DEPTH INCLUDED IN GENERATION OUTPUT (per your request)
# -------------------------------------------------------------
GENERATION_PARAMS = [
    "Concentric Duration [ms]",              # PD
    "Countermovement Depth [cm]",            # DEP (now included)
    "Concentric Mean Force / BM [N/kg]",     # PF
]

ABSORPTION_PARAMS = [
    "Braking Phase Duration [ms]",           # BD
    "Countermovement Depth [cm]",            # DEP
    "Eccentric Mean Force / BM [N/kg]",      # BF (created below)
]

OTHER_PARAMS = [
    "BW [KG]",
    "Jump Height (Imp-Mom) [cm]",
]

# -------------------------------------------------------------
# 4. COERCE BASE NUMERICS
# -------------------------------------------------------------
if "BW [KG]" not in df.columns:
    raise SystemExit("Required column 'BW [KG]' not found.")
df["BW [KG]"] = pd.to_numeric(df["BW [KG]"], errors="coerce")

# Coerce any existing fields to numeric
for c in (GENERATION_PARAMS + OTHER_PARAMS + ["Eccentric Deceleration Mean Force [N]"]):
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

# -------------------------------------------------------------
# 5. CREATE Eccentric Mean Force / BM [N/kg] (ROUNDED 1 DECIMAL)
#    = Eccentric Deceleration Mean Force [N] / BW [KG]
# -------------------------------------------------------------
needed = ["Eccentric Deceleration Mean Force [N]", "BW [KG]"]
for col in needed:
    if col not in df.columns:
        raise SystemExit(
            f"Required column {col!r} not found.\n"
            f"Available columns: {df.columns.tolist()}"
        )

df["Eccentric Mean Force / BM [N/kg]"] = (
    df["Eccentric Deceleration Mean Force [N]"] / df["BW [KG]"]
).round(1)

# -------------------------------------------------------------
# 6. FINALIZE PARAM LISTS (include created column)
# -------------------------------------------------------------
ALL_PARAMS = list(dict.fromkeys(GENERATION_PARAMS + ABSORPTION_PARAMS + OTHER_PARAMS))
ALL_PARAMS = [p for p in ALL_PARAMS if p in df.columns]

GENERATION_PARAMS = [p for p in GENERATION_PARAMS if p in ALL_PARAMS]
ABSORPTION_PARAMS = [p for p in ABSORPTION_PARAMS if p in ALL_PARAMS]
OTHER_PARAMS      = [p for p in OTHER_PARAMS      if p in ALL_PARAMS]

print("Generation parameters:", GENERATION_PARAMS)
print("Absorption parameters:", ABSORPTION_PARAMS)
print("Standalone classified params:", OTHER_PARAMS)

# -------------------------------------------------------------
# 7. TREAT 0 AS MISSING FOR CMJ METRICS
# -------------------------------------------------------------
for c in ALL_PARAMS:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[df[c] == 0, c] = np.nan

# -------------------------------------------------------------
# 8. PARAMETER-LEVEL ROLLING CLASSIFICATION
#    - ignore missing days
#    - first 2 valid trials per player+param => z=0 => class Avg
#    - add "{param}_avg_prev" rounded 1 decimal
#
# IMPORTANT: Depth is now POSITIVE in your dataset:
#   High depth = deeper = bigger value => z>=1 => High
#   Low  depth = shallower = smaller value => z<=-1 => Low
# -------------------------------------------------------------
def classify_z(z):
    if pd.isna(z):
        return "Avg"
    if z >= 1:
        return "High"
    if z <= -1:
        return "Low"
    return "Avg"

for param in ALL_PARAMS:
    if param not in df.columns:
        continue

    g = df.groupby(PLAYER_COL)[param]

    count_prev = (
        g.apply(lambda s: s.expanding(min_periods=1).count().shift(1))
         .reset_index(level=0, drop=True)
    )

    mean_prev = (
        g.apply(lambda s: s.expanding(min_periods=1).mean().shift(1))
         .reset_index(level=0, drop=True)
    )

    sd_prev = (
        g.apply(lambda s: s.expanding(min_periods=2).std(ddof=1).shift(1))
         .reset_index(level=0, drop=True)
    )

    # prior average column, rounded
    df[f"{param}_avg_prev"] = mean_prev.round(1)

    z_raw = (df[param] - mean_prev) / sd_prev
    z = pd.Series(np.nan, index=df.index, dtype="float64")

    has_current = df[param].notna()
    enough_history = count_prev.ge(2)
    sd_ok = sd_prev.notna() & (sd_prev != 0)

    mask_normal = has_current & enough_history & sd_ok
    z.loc[mask_normal] = z_raw.loc[mask_normal]

    # first two valid trials OR sd missing/0 => Avg
    mask_force_avg = has_current & (~enough_history | ~sd_ok)
    z.loc[mask_force_avg] = 0.0

    df[f"{param}_z"] = z
    df[f"{param}_class"] = df[f"{param}_z"].apply(classify_z)

# -------------------------------------------------------------
# 9. DAY-LEVEL GENERATION & ABSORPTION CLASSIFICATION
#    - if required RAW inputs missing => overall class blank
#    - NEW: Generation overall now uses PD + DEP + PF with your updated logic
#    - NEW: Absorption overall uses BD + DEP + BF with your updated logic
# -------------------------------------------------------------
def classify_generation(pd_class, dep_class, pf_class):
    if pd.isna(pd_class) or pd.isna(dep_class) or pd.isna(pf_class):
        return ""
    PD, DEP, PF = str(pd_class), str(dep_class), str(pf_class)

    # If PD & DEP both HIGH:
    if PD == "High" and DEP == "High":
        if PF == "High":
            return "Avg"
        if PF in ("Low", "Avg"):
            return "Low"

    # If PD & DEP both LOW:
    if PD == "Low" and DEP == "Low":
        if PF == "Low":
            return "Avg"
        if PF in ("High", "Avg"):
            return "High"

    # If exactly one of PD / DEP is HIGH:
    if (PD == "High" and DEP == "Avg") or (PD == "Avg" and DEP == "High"):
        if PD == "High" and DEP == "Avg":
            # PD High + DEP Avg
            if PF in ("Avg", "Low"):
                return "Low"
            if PF == "High":
                return "High"
        else:
            # DEP High + PD Avg
            if PF in ("Avg", "High"):
                return "High"
            if PF == "Low":
                return "Low"

    # If exactly one of PD / DEP is LOW:
    if (PD == "Low" and DEP == "Avg") or (PD == "Avg" and DEP == "Low"):
        if PD == "Low" and DEP == "Avg":
            if PF == "Low":
                return "Low"
            # PF Avg or High
            return "High"
        else:
            # DEP Low + PD Avg
            if PF in ("Avg", "Low"):
                return "Low"
            if PF == "High":
                return "High"

    # PD & DEP both NORMAL:
    if PD == "Avg" and DEP == "Avg":
        if PF == "High":
            return "High"
        if PF == "Low":
            return "Low"
        return "Avg"

    # If one HIGH, one LOW (PD vs DEP):
    if PD == "Low" and DEP == "High":
        return "High"
    if PD == "High" and DEP == "Low":
        return "Low"

    return "Avg"

def classify_absorption(bd_class, dep_class, bf_class):
    if pd.isna(bd_class) or pd.isna(dep_class) or pd.isna(bf_class):
        return ""
    BD, DEP, BF = str(bd_class), str(dep_class), str(bf_class)

    # If BD & DEP both HIGH:
    if BD == "High" and DEP == "High":
        if BF == "High":
            return "Avg"
        # BF Avg or Low
        return "High"

    # If BD & DEP both LOW:
    if BD == "Low" and DEP == "Low":
        if BF == "Low":
            return "Avg"
        # BF Avg or High
        return "Low"

    # If exactly one of BD/DEP is HIGH:
    if (BD == "High" and DEP == "Avg") or (BD == "Avg" and DEP == "High"):
        if BD == "High" and DEP == "Avg":
            if BF in ("Avg", "Low"):
                return "Low"
            if BF == "High":
                return "High"
        else:
            # DEP High + BD Avg
            if BF in ("Avg", "High"):
                return "High"
            if BF == "Low":
                return "Low"

    # If exactly one of BD/DEP is LOW:
    if (BD == "Low" and DEP == "Avg") or (BD == "Avg" and DEP == "Low"):
        if BD == "Low" and DEP == "Avg":
            if BF == "Low":
                return "Low"
            # BF Avg or High
            return "High"
        else:
            # DEP Low + BD Avg
            if BF in ("Avg", "Low"):
                return "Low"
            if BF == "High":
                return "High"

    # BD & DEP both NORMAL:
    if BD == "Avg" and DEP == "Avg":
        if BF == "High":
            return "High"
        if BF == "Low":
            return "Low"
        return "Avg"

    # If one HIGH, one LOW (BD vs DEP):
    if BD == "Low" and DEP == "High":
        return "High"
    if BD == "High" and DEP == "Low":
        return "Low"

    return "Avg"

# Column handles
pd_col    = "Concentric Duration [ms]"
pf_col    = "Concentric Mean Force / BM [N/kg]"
bd_col    = "Braking Phase Duration [ms]"
dep_col   = "Countermovement Depth [cm]"
bf_col    = "Eccentric Mean Force / BM [N/kg]"

pd_class_col = f"{pd_col}_class"
pf_class_col = f"{pf_col}_class"
bd_class_col = f"{bd_col}_class"
dep_class_col = f"{dep_col}_class"
bf_class_col = f"{bf_col}_class"

df["Generation_Class"] = ""
df["Absorption_Class"] = ""

required_gen_raw = [c for c in [pd_col, dep_col, pf_col] if c in df.columns]
required_abs_raw = [c for c in [bd_col, dep_col, bf_col] if c in df.columns]

if required_gen_raw:
    mask_gen = df[required_gen_raw].notna().all(axis=1)
    df.loc[mask_gen, "Generation_Class"] = df.loc[mask_gen].apply(
        lambda r: classify_generation(r.get(pd_class_col), r.get(dep_class_col), r.get(pf_class_col)),
        axis=1
    )

if required_abs_raw:
    mask_abs = df[required_abs_raw].notna().all(axis=1)
    df.loc[mask_abs, "Absorption_Class"] = df.loc[mask_abs].apply(
        lambda r: classify_absorption(r.get(bd_class_col), r.get(dep_class_col), r.get(bf_class_col)),
        axis=1
    )

# -------------------------------------------------------------
# 10. DROP ROWS WITH NO CMJ DATA
# -------------------------------------------------------------
DATA_GATE_COLS = []
for c in (["Jump Height (Imp-Mom) [cm]"] + GENERATION_PARAMS + ABSORPTION_PARAMS):
    if c in df.columns and c != "BW [KG]":
        DATA_GATE_COLS.append(c)
DATA_GATE_COLS = list(dict.fromkeys(DATA_GATE_COLS))

if DATA_GATE_COLS:
    CMJ_DATA_MASK = df[DATA_GATE_COLS].notna().any(axis=1)
else:
    CMJ_DATA_MASK = pd.Series(True, index=df.index)

df = df.loc[CMJ_DATA_MASK].copy()

# -------------------------------------------------------------
# 11. BUILD GENERATION & ABSORPTION DATAFRAMES
#     - Generation now includes Depth (same values/classes as absorption)
# -------------------------------------------------------------
base_cols = [PLAYER_COL, DATE_COL]

gen_value_params = GENERATION_PARAMS + OTHER_PARAMS
abs_value_params = ABSORPTION_PARAMS + OTHER_PARAMS

gen_cols = (
    base_cols
    + gen_value_params
    + [f"{p}_avg_prev" for p in gen_value_params if f"{p}_avg_prev" in df.columns]
    + [f"{p}_z" for p in gen_value_params if f"{p}_z" in df.columns]
    + [f"{p}_class" for p in gen_value_params if f"{p}_class" in df.columns]
    + ["Generation_Class"]
)

abs_cols = (
    base_cols
    + abs_value_params
    + [f"{p}_avg_prev" for p in abs_value_params if f"{p}_avg_prev" in df.columns]
    + [f"{p}_z" for p in abs_value_params if f"{p}_z" in df.columns]
    + [f"{p}_class" for p in abs_value_params if f"{p}_class" in df.columns]
    + ["Absorption_Class"]
)

gen_cols = [c for c in gen_cols if c in df.columns]
abs_cols = [c for c in abs_cols if c in df.columns]

df_gen = df[gen_cols].copy()
df_abs = df[abs_cols].copy()

# -------------------------------------------------------------
# 12. TEAM-LEVEL SNAPSHOT (TTD, LTD, BW, JH, ABS, GEN)
# -------------------------------------------------------------
agg = (
    df.groupby(PLAYER_COL)[DATE_COL]
      .agg(TTD="count", LTD="max")
      .reset_index()
)

last_idx = df.groupby(PLAYER_COL)[DATE_COL].idxmax()

cols_last = [
    PLAYER_COL,
    DATE_COL,
    "BW [KG]",
    "BW [KG]_class",
    "Jump Height (Imp-Mom) [cm]",
    "Jump Height (Imp-Mom) [cm]_class",
    "Absorption_Class",
    "Generation_Class",
]
cols_last = [c for c in cols_last if c in df.columns]

df_last = df.loc[last_idx, cols_last].rename(columns={DATE_COL: "LTD"})

team_df = agg.merge(df_last, on=[PLAYER_COL, "LTD"], how="left")
team_df = team_df.sort_values("LTD", ascending=False)

team_out_cols = [PLAYER_COL, "TTD", "LTD", "BW [KG]", "Jump Height (Imp-Mom) [cm]", "Absorption_Class", "Generation_Class"]
team_out_cols = [c for c in team_out_cols if c in team_df.columns]

team_df[team_out_cols].to_csv(OUTPUT_TEAM_CSV, index=False)
print("Saved Team snapshot CSV to:", OUTPUT_TEAM_CSV)

# -------------------------------------------------------------
# 13. SAVE CSVs
# -------------------------------------------------------------
df_gen.to_csv(OUTPUT_GEN_CSV, index=False)
df_abs.to_csv(OUTPUT_ABS_CSV, index=False)
print("Saved Generation CSV to:", OUTPUT_GEN_CSV)
print("Saved Absorption CSV to:", OUTPUT_ABS_CSV)

# -------------------------------------------------------------
# 14. PDF SETTINGS (COLORS, LABELS)
# -------------------------------------------------------------
os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)

COLOR_MAP = {
    "High": {"face": "#FF7276", "text": "black"},
    "Low":  {"face": "#87CEEB", "text": "#305CDE"},
    "Avg":  {"face": "#D3D3D3", "text": "black"},
    "":     {"face": "white",   "text": "black"},
}

DISPLAY_LABELS = {
    PLAYER_COL: "PLAYER",
    "Concentric Duration [ms]": "Propulsive\nDuration",
    "Concentric Mean Force / BM [N/kg]": "Propulsive\nForce",
    "Braking Phase Duration [ms]": "Braking\nDuration",
    "Countermovement Depth [cm]": "Squat\nDepth",
    "Eccentric Mean Force / BM [N/kg]": "Braking\nForce",
    "BW [KG]": "Weight[kg]",
    "Jump Height (Imp-Mom) [cm]": "Jump\nHeight",
    "Generation_Class": "Generation\nOVR",
    "Absorption_Class": "Absorption\nOVR",
    "TTD": "Total\nTesting Days",
    "LTD": "Last\nTesting Date",
    DATE_COL: "Date",
}

def display_name(col):
    if col.endswith("_avg_prev"):
        base = col.replace("_avg_prev", "")
        return f"{DISPLAY_LABELS.get(base, base)}\nAvg(prev)"
    return DISPLAY_LABELS.get(col, col)

def format_value(col, val):
    if pd.isna(val) or val == "":
        return ""
    if col in (DATE_COL, "LTD"):
        return pd.to_datetime(val).strftime("%Y-%m-%d")
    if col == "TTD":
        return f"{int(val)}"
    if col in ["Concentric Duration [ms]", "Braking Phase Duration [ms]"]:
        try:
            return f"{int(round(float(val)))}"
        except Exception:
            return str(val)
    try:
        return f"{float(val):.1f}"
    except Exception:
        return str(val)

def class_to_arrow(text):
    if text == "High":
        return "↑"
    if text == "Low":
        return "↓"
    if text == "Avg":
        return "→"
    return ""

def add_table_page(pdf, player_name, title, df_player, value_cols, class_map):
    if df_player.empty:
        return

    df_player = df_player.sort_values(DATE_COL, ascending=False)

    cols = [DATE_COL] + value_cols
    header_labels = [display_name(c) for c in cols]

    data_rows = []
    for _, row in df_player.iterrows():
        row_vals = [format_value(DATE_COL, row[DATE_COL])]
        for col in value_cols:
            raw_val = row.get(col, "")
            disp = format_value(col, raw_val)
            if col in ("Generation_Class", "Absorption_Class"):
                disp = class_to_arrow(disp)
            row_vals.append(disp)
        data_rows.append(row_vals)

    n_rows = len(data_rows)
    n_cols = len(cols)

    fig_width  = max(8, n_cols * 1.3)
    fig_height = max(4, n_rows * 0.4 + 2)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis("off")

    table = ax.table(cellText=data_rows, colLabels=header_labels, loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.1, 1.3)

    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_facecolor("black")
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")

    for r_idx, (_, row) in enumerate(df_player.iterrows(), start=1):
        for c_idx, col in enumerate(cols):
            if col == DATE_COL:
                continue
            cell = table[r_idx, c_idx]
            class_source = class_map.get(col)
            cls = row.get(class_source, "Avg") if class_source else "Avg"
            if cls not in COLOR_MAP:
                cls = "Avg"
            colors = COLOR_MAP[cls]
            cell.set_facecolor(colors["face"])
            cell.get_text().set_color(colors["text"])

    ax.set_title(f"{player_name} - {title} Classification", fontsize=12, pad=12)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)

def add_team_overview(pdf, team_df_in):
    if team_df_in.empty:
        return

    df_team = team_df_in.sort_values("LTD", ascending=False)

    cols = [
        PLAYER_COL,
        "TTD",
        "LTD",
        "BW [KG]",
        "Jump Height (Imp-Mom) [cm]",
        "Absorption_Class",
        "Generation_Class",
    ]
    cols = [c for c in cols if c in df_team.columns]
    header_labels = [display_name(c) for c in cols]

    data_rows = []
    for _, row in df_team.iterrows():
        row_vals = []
        for col in cols:
            raw_val = row.get(col, "")
            disp = format_value(col, raw_val)
            if col in ("Absorption_Class", "Generation_Class"):
                disp = class_to_arrow(disp)
            row_vals.append(disp)
        data_rows.append(row_vals)

    n_rows = len(data_rows)
    n_cols = len(cols)

    fig_width  = max(8, n_cols * 1.3)
    fig_height = max(4, n_rows * 0.4 + 2)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis("off")

    table = ax.table(cellText=data_rows, colLabels=header_labels, loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.1, 1.3)

    try:
        table.auto_set_column_width(col=list(range(n_cols)))
    except Exception:
        pass

    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_facecolor("black")
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")

    class_map_team = {
        "BW [KG]": "BW [KG]_class",
        "Jump Height (Imp-Mom) [cm]": "Jump Height (Imp-Mom) [cm]_class",
        "Absorption_Class": "Absorption_Class",
        "Generation_Class": "Generation_Class",
    }

    for r_idx, (_, row) in enumerate(df_team.iterrows(), start=1):
        for c_idx, col in enumerate(cols):
            if col in [PLAYER_COL, "TTD", "LTD"]:
                continue
            cell = table[r_idx, c_idx]
            source = class_map_team.get(col)
            cls = row.get(source, "Avg") if source else "Avg"
            if cls not in COLOR_MAP:
                cls = "Avg"
            colors = COLOR_MAP[cls]
            cell.set_facecolor(colors["face"])
            cell.get_text().set_color(colors["text"])

    ax.set_title("CMJ Team Overview (Latest Test Per Player)", fontsize=12, pad=12)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)

# -------------------------------------------------------------
# 15. BUILD PER-PLAYER & TEAM PDFs
# -------------------------------------------------------------
unique_players = df[PLAYER_COL].dropna().unique()

for player in unique_players:
    safe_name = str(player).replace("/", "_").replace("\\", "_")
    pdf_path = os.path.join(PDF_OUTPUT_DIR, f"{safe_name}_CMJ_Classification.pdf")

    df_gen_p = df_gen[df_gen[PLAYER_COL] == player]
    df_abs_p = df_abs[df_abs[PLAYER_COL] == player]

    gen_value_cols = ["Generation_Class", "BW [KG]", "Jump Height (Imp-Mom) [cm]"] + GENERATION_PARAMS
    abs_value_cols = ["Absorption_Class", "BW [KG]", "Jump Height (Imp-Mom) [cm]"] + ABSORPTION_PARAMS

    gen_class_map = {
        "Generation_Class": "Generation_Class",
        "BW [KG]": "BW [KG]_class",
        "Jump Height (Imp-Mom) [cm]": "Jump Height (Imp-Mom) [cm]_class",
        "Concentric Duration [ms]": "Concentric Duration [ms]_class",
        "Countermovement Depth [cm]": "Countermovement Depth [cm]_class",
        "Concentric Mean Force / BM [N/kg]": "Concentric Mean Force / BM [N/kg]_class",
    }

    abs_class_map = {
        "Absorption_Class": "Absorption_Class",
        "BW [KG]": "BW [KG]_class",
        "Jump Height (Imp-Mom) [cm]": "Jump Height (Imp-Mom) [cm]_class",
        "Braking Phase Duration [ms]": "Braking Phase Duration [ms]_class",
        "Countermovement Depth [cm]": "Countermovement Depth [cm]_class",
        "Eccentric Mean Force / BM [N/kg]": "Eccentric Mean Force / BM [N/kg]_class",
    }

    with PdfPages(pdf_path) as pdf:
        add_table_page(pdf, player, "Generation", df_gen_p, gen_value_cols, gen_class_map)
        add_table_page(pdf, player, "Absorption", df_abs_p, abs_value_cols, abs_class_map)

    print(f"Saved player PDF: {pdf_path}")

with PdfPages(TEAM_PDF_PATH) as pdf:
    add_team_overview(pdf, team_df)

print(f"Saved team overview PDF: {TEAM_PDF_PATH}")
