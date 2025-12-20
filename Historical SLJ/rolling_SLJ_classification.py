import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# -------------------------------------------------------------
# FILE PATHS (SINGLE-LEG JUMP)
# -------------------------------------------------------------
ROOT = r"C:\Example Data\VALD Jump Exports\Historical SLJ"
INPUT_FILE        = os.path.join(ROOT, "raw_VALD_slj.csv")

OUTPUT_GEN_CSV_L  = os.path.join(ROOT, "L_Generation_Daily_Classes.csv")
OUTPUT_ABS_CSV_L  = os.path.join(ROOT, "L_Absorption_Daily_Classes.csv")
OUTPUT_TEAM_CSV_L = os.path.join(ROOT, "Team_LSLJ_Snapshot.csv")

OUTPUT_GEN_CSV_R  = os.path.join(ROOT, "R_Generation_Daily_Classes.csv")
OUTPUT_ABS_CSV_R  = os.path.join(ROOT, "R_Absorption_Daily_Classes.csv")
OUTPUT_TEAM_CSV_R = os.path.join(ROOT, "Team_RSLJ_Snapshot.csv")

PDF_OUTPUT_DIR    = os.path.join(ROOT, "Player_PDFs")
TEAM_PDF_PATH     = os.path.join(ROOT, "SLJ_Team_Overview.pdf")

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
# 3. DEFINE PARAMETER SETS FOR L & R
# -------------------------------------------------------------
GENERATION_PARAMS = {}
ABSORPTION_PARAMS = {}
OTHER_PARAMS = {}
ALL_PARAMS = []

for leg in ["L", "R"]:
    gen_params = [
        f"Concentric Duration [ms] ({leg})",
        f"Concentric Mean Force / BM [N/kg] ({leg})",
    ]
    abs_params = [
        f"Braking Phase Duration [ms] ({leg})",
        f"Countermovement Depth [cm] ({leg})",
        f"Eccentric Mean Force / BM [N/kg] ({leg})",  # will be created below
    ]
    other_params = [
        "BW [KG]",
        f"Jump Height (Imp-Mom) [cm] ({leg})",
    ]

    gen_params   = [p for p in gen_params   if p in df.columns]
    abs_params   = [p for p in abs_params   if (p in df.columns) or ("Eccentric Mean Force / BM" in p)]
    other_params = [p for p in other_params if p in df.columns]

    GENERATION_PARAMS[leg] = gen_params
    ABSORPTION_PARAMS[leg] = abs_params
    OTHER_PARAMS[leg] = other_params

    ALL_PARAMS.extend(gen_params + abs_params + other_params)

ALL_PARAMS = list(dict.fromkeys(ALL_PARAMS))

# -------------------------------------------------------------
# 4. COERCE BASE NUMERICS (INCLUDING BW) BEFORE DERIVED METRICS
# -------------------------------------------------------------
if "BW [KG]" not in df.columns:
    raise SystemExit("Required column 'BW [KG]' not found.")
df["BW [KG]"] = pd.to_numeric(df["BW [KG]"], errors="coerce")

for c in list(set(ALL_PARAMS + ["BW [KG]"])):
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

# -------------------------------------------------------------
# 5. CREATE ECCENTRIC MEAN FORCE / BM FOR L & R (ROUNDED 1 DECIMAL)
# -------------------------------------------------------------
for leg in ["L", "R"]:
    edf_col = f"Eccentric Deceleration Mean Force [N] ({leg})"
    emf_col = f"Eccentric Mean Force / BM [N/kg] ({leg})"

    if edf_col not in df.columns:
        raise SystemExit(
            f"Required column {edf_col!r} not found.\n"
            f"Available columns: {df.columns.tolist()}"
        )

    df[edf_col] = pd.to_numeric(df[edf_col], errors="coerce")
    df[emf_col] = (df[edf_col] / df["BW [KG]"]).round(1)

    if emf_col not in ALL_PARAMS:
        ALL_PARAMS.append(emf_col)
    if emf_col not in ABSORPTION_PARAMS[leg]:
        ABSORPTION_PARAMS[leg].append(emf_col)

# -------------------------------------------------------------
# 6. TREAT 0 AS MISSING FOR SLJ METRICS
# -------------------------------------------------------------
for c in ALL_PARAMS:
    if c in df.columns:
        df.loc[df[c] == 0, c] = np.nan

print("Generation parameters:", GENERATION_PARAMS)
print("Absorption parameters:", ABSORPTION_PARAMS)
print("Standalone classified params:", OTHER_PARAMS)

# -------------------------------------------------------------
# 7. PARAMETER-LEVEL ROLLING CLASSIFICATION
#    - ignore missing
#    - first 2 valid trials per player+param => z=0 => class Avg
#    - avg_prev rounded 1 decimal
# -------------------------------------------------------------
def classify_z(z):
    if pd.isna(z):
        return "Avg"
    if z >= 1:
        return "High"
    if z <= -1:
        return "Low"
    return "Avg"

def classify_depth_z(z):
    if pd.isna(z):
        return "Avg"
    if z <= -1:
        return "High"
    if z >= 1:
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

    df[f"{param}_avg_prev"] = mean_prev.round(1)

    z_raw = (df[param] - mean_prev) / sd_prev

    # IMPORTANT FIX: init with np.nan, not pd.NA, for float series
    z = pd.Series(np.nan, index=df.index, dtype="float64")

    has_current = df[param].notna()
    enough_history = count_prev.ge(2)
    sd_ok = sd_prev.notna() & (sd_prev != 0)

    mask_normal = has_current & enough_history & sd_ok
    z.loc[mask_normal] = z_raw.loc[mask_normal]

    # early trials OR sd==0 OR sd missing => force Avg via z=0
    mask_force_avg = has_current & (~enough_history | ~sd_ok)
    z.loc[mask_force_avg] = 0.0

    df[f"{param}_z"] = z

    if "Countermovement Depth [cm]" in param:
        df[f"{param}_class"] = df[f"{param}_z"].apply(classify_depth_z)
    else:
        df[f"{param}_class"] = df[f"{param}_z"].apply(classify_z)

# -------------------------------------------------------------
# 8. DAY-LEVEL GENERATION & ABSORPTION CLASSIFICATION PER LEG
#    - if leg raw inputs missing => overall leg class blank
# -------------------------------------------------------------
def classify_generation(dur_class, force_class):
    if pd.isna(dur_class) or pd.isna(force_class):
        return ""
    d, f = dur_class, force_class

    if d == "Avg" and f == "Avg":
        return "Avg"

    if d == "Avg" and f == "Low":
        return "Low"
    if d == "High" and f == "Avg":
        return "Low"
    if d == "High" and f == "Low":
        return "Low"
    if d == "Low" and f == "Low":
        return "Low"

    if d == "High" and f == "High":
        return "High"
    if d == "Low" and f == "Avg":
        return "High"
    if d == "Avg" and f == "High":
        return "High"
    if d == "Low" and f == "High":
        return "High"

    return "Avg"

def classify_absorption(bd_class, dep_class, bf_class):
    if pd.isna(bd_class) or pd.isna(dep_class) or pd.isna(bf_class):
        return ""
    BD, DEP, BF = bd_class, dep_class, bf_class

    if BD == "High" and DEP == "High":
        return "High"
    if BD == "Low" and DEP == "Low":
        return "Low"

    if BD == "Low" and DEP == "High":
        return "High"
    if BD == "High" and DEP == "Low":
        return "Low"

    if BD == "High" and DEP == "Avg":
        return "Low"

    if BD == "Avg" and DEP == "High":
        return "Low" if BF == "Low" else "High"

    if BD == "Low" and DEP == "Avg":
        return "Low" if BF == "Low" else "High"

    if BD == "Avg" and DEP == "Low":
        return "High" if BF == "High" else "Low"

    if BD == "Avg" and DEP == "Avg":
        if BF == "High":
            return "High"
        if BF == "Low":
            return "Low"
        return "Avg"

    return "Avg"

for leg in ["L", "R"]:
    dur_col   = f"Concentric Duration [ms] ({leg})"
    force_col = f"Concentric Mean Force / BM [N/kg] ({leg})"
    bd_col    = f"Braking Phase Duration [ms] ({leg})"
    dep_col   = f"Countermovement Depth [cm] ({leg})"
    bf_col    = f"Eccentric Mean Force / BM [N/kg] ({leg})"

    dur_class_col   = f"{dur_col}_class"
    force_class_col = f"{force_col}_class"
    bd_class_col    = f"{bd_col}_class"
    dep_class_col   = f"{dep_col}_class"
    bf_class_col    = f"{bf_col}_class"

    gen_col = f"Generation_Class_{leg}"
    abs_col = f"Absorption_Class_{leg}"

    required_gen_raw = [c for c in [dur_col, force_col] if c in df.columns]
    required_abs_raw = [c for c in [bd_col, dep_col, bf_col] if c in df.columns]

    df[gen_col] = ""
    df[abs_col] = ""

    if required_gen_raw:
        mask_gen = df[required_gen_raw].notna().all(axis=1)
        df.loc[mask_gen, gen_col] = df.loc[mask_gen].apply(
            lambda r: classify_generation(r.get(dur_class_col), r.get(force_class_col)),
            axis=1
        )

    if required_abs_raw:
        mask_abs = df[required_abs_raw].notna().all(axis=1)
        df.loc[mask_abs, abs_col] = df.loc[mask_abs].apply(
            lambda r: classify_absorption(r.get(bd_class_col), r.get(dep_class_col), r.get(bf_class_col)),
            axis=1
        )

# -------------------------------------------------------------
# 9. BUILD LEG-SPECIFIC FILTERS (DROP ROWS WITH NO LEG DATA)
# -------------------------------------------------------------
LEG_DATA_MASK = {}
for leg in ["L", "R"]:
    leg_cols = []

    jh_col = f"Jump Height (Imp-Mom) [cm] ({leg})"
    if jh_col in df.columns:
        leg_cols.append(jh_col)

    leg_cols += [c for c in GENERATION_PARAMS[leg] if c in df.columns and c != "BW [KG]"]
    leg_cols += [c for c in ABSORPTION_PARAMS[leg] if c in df.columns and c != "BW [KG]"]

    leg_cols = list(dict.fromkeys([c for c in leg_cols if c in df.columns]))

    if not leg_cols:
        LEG_DATA_MASK[leg] = pd.Series(True, index=df.index)
    else:
        LEG_DATA_MASK[leg] = df[leg_cols].notna().any(axis=1)

# -------------------------------------------------------------
# 10. BUILD PER-LEG OUTPUT DATAFRAMES
# -------------------------------------------------------------
base_cols = [PLAYER_COL, DATE_COL]
df_gen_leg = {}
df_abs_leg = {}

for leg in ["L", "R"]:
    gen_params   = GENERATION_PARAMS[leg]
    abs_params   = ABSORPTION_PARAMS[leg]
    other_params = OTHER_PARAMS[leg]

    gen_value_params = gen_params + other_params
    abs_value_params = abs_params + other_params

    gen_cols = (
        base_cols
        + gen_value_params
        + [f"{p}_avg_prev" for p in gen_value_params if f"{p}_avg_prev" in df.columns]
        + [f"{p}_z" for p in gen_value_params if f"{p}_z" in df.columns]
        + [f"{p}_class" for p in gen_value_params if f"{p}_class" in df.columns]
        + [f"Generation_Class_{leg}"]
    )
    abs_cols = (
        base_cols
        + abs_value_params
        + [f"{p}_avg_prev" for p in abs_value_params if f"{p}_avg_prev" in df.columns]
        + [f"{p}_z" for p in abs_value_params if f"{p}_z" in df.columns]
        + [f"{p}_class" for p in abs_value_params if f"{p}_class" in df.columns]
        + [f"Absorption_Class_{leg}"]
    )

    gen_cols = [c for c in gen_cols if c in df.columns]
    abs_cols = [c for c in abs_cols if c in df.columns]

    mask_leg = LEG_DATA_MASK[leg]
    df_gen_leg[leg] = df.loc[mask_leg, gen_cols].copy()
    df_abs_leg[leg] = df.loc[mask_leg, abs_cols].copy()

# -------------------------------------------------------------
# 11. TEAM-LEVEL SNAPSHOT PER LEG
# -------------------------------------------------------------
agg = (
    df.groupby(PLAYER_COL)[DATE_COL]
      .agg(TTD="count", LTD="max")
      .reset_index()
)

team_df_leg = {}

for leg in ["L", "R"]:
    jh_col       = f"Jump Height (Imp-Mom) [cm] ({leg})"
    jh_class_col = f"{jh_col}_class"
    gen_col      = f"Generation_Class_{leg}"
    abs_col      = f"Absorption_Class_{leg}"

    df_leg = df.loc[LEG_DATA_MASK[leg]].copy()
    if df_leg.empty:
        last_idx = df.groupby(PLAYER_COL)[DATE_COL].idxmax()
        df_last_leg_source = df.loc[last_idx].copy()
    else:
        last_idx_leg = df_leg.groupby(PLAYER_COL)[DATE_COL].idxmax()
        df_last_leg_source = df.loc[last_idx_leg].copy()

    cols_needed = [
        PLAYER_COL, DATE_COL,
        "BW [KG]", "BW [KG]_class",
        jh_col, jh_class_col,
        gen_col, abs_col,
    ]
    cols_needed = [c for c in cols_needed if c in df_last_leg_source.columns]

    df_last_leg = df_last_leg_source[cols_needed].rename(columns={DATE_COL: "LTD"})

    team_df = agg.merge(df_last_leg, on=[PLAYER_COL, "LTD"], how="left")
    team_df = team_df.sort_values("LTD", ascending=False)
    team_df_leg[leg] = team_df

    out_cols = [PLAYER_COL, "TTD", "LTD", "BW [KG]", jh_col, abs_col, gen_col]
    out_cols = [c for c in out_cols if c in team_df.columns]

    if leg == "L":
        team_df[out_cols].to_csv(OUTPUT_TEAM_CSV_L, index=False)
        print("Saved Left Team snapshot CSV to:", OUTPUT_TEAM_CSV_L)
    else:
        team_df[out_cols].to_csv(OUTPUT_TEAM_CSV_R, index=False)
        print("Saved Right Team snapshot CSV to:", OUTPUT_TEAM_CSV_R)

# -------------------------------------------------------------
# 12. SAVE PER-LEG CSVs
# -------------------------------------------------------------
df_gen_leg["L"].to_csv(OUTPUT_GEN_CSV_L, index=False)
df_abs_leg["L"].to_csv(OUTPUT_ABS_CSV_L, index=False)
print("Saved Left Generation CSV to:", OUTPUT_GEN_CSV_L)
print("Saved Left Absorption CSV to:", OUTPUT_ABS_CSV_L)

df_gen_leg["R"].to_csv(OUTPUT_GEN_CSV_R, index=False)
df_abs_leg["R"].to_csv(OUTPUT_ABS_CSV_R, index=False)
print("Saved Right Generation CSV to:", OUTPUT_GEN_CSV_R)
print("Saved Right Absorption CSV to:", OUTPUT_ABS_CSV_R)

# -------------------------------------------------------------
# 13. PDF SETTINGS (COLORS, LABELS)
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
    "Concentric Duration [ms] (L)": "Propulsive\nDuration",
    "Concentric Duration [ms] (R)": "Propulsive\nDuration",
    "Concentric Mean Force / BM [N/kg] (L)": "Propulsive\nForce",
    "Concentric Mean Force / BM [N/kg] (R)": "Propulsive\nForce",
    "Braking Phase Duration [ms] (L)": "Braking\nDuration",
    "Braking Phase Duration [ms] (R)": "Braking\nDuration",
    "Countermovement Depth [cm] (L)": "Squat\nDepth",
    "Countermovement Depth [cm] (R)": "Squat\nDepth",
    "Eccentric Mean Force / BM [N/kg] (L)": "Braking\nForce",
    "Eccentric Mean Force / BM [N/kg] (R)": "Braking\nForce",
    "BW [KG]": "Weight[kg]",
    "Jump Height (Imp-Mom) [cm] (L)": "Jump\nHeight",
    "Jump Height (Imp-Mom) [cm] (R)": "Jump\nHeight",
    "Generation_Class_L": "Generation\nOVR",
    "Generation_Class_R": "Generation\nOVR",
    "Absorption_Class_L": "Absorption\nOVR",
    "Absorption_Class_R": "Absorption\nOVR",
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
    if "Concentric Duration [ms]" in col or "Braking Phase Duration [ms]" in col:
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
            if col in ("Generation_Class_L", "Absorption_Class_L",
                       "Generation_Class_R", "Absorption_Class_R"):
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

    ax.set_title(f"{player_name} - {title}", fontsize=12, pad=12)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)

def add_team_overview_leg(pdf, team_df_in, leg_label, leg):
    if team_df_in.empty:
        return

    df_team = team_df_in.sort_values("LTD", ascending=False)

    jh_col = f"Jump Height (Imp-Mom) [cm] ({leg})"
    gen_col = f"Generation_Class_{leg}"
    abs_col = f"Absorption_Class_{leg}"

    cols = [PLAYER_COL, "TTD", "LTD", "BW [KG]", jh_col, abs_col, gen_col]
    cols = [c for c in cols if c in df_team.columns]
    header_labels = [display_name(c) for c in cols]

    data_rows = []
    for _, row in df_team.iterrows():
        row_vals = []
        for col in cols:
            raw_val = row.get(col, "")
            disp = format_value(col, raw_val)
            if col in (abs_col, gen_col):
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
        jh_col: f"{jh_col}_class",
        abs_col: abs_col,
        gen_col: gen_col,
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

    ax.set_title(f"SLJ Team Overview - {leg_label}", fontsize=12, pad=12)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)

# -------------------------------------------------------------
# 14. BUILD PER-PLAYER & TEAM PDFs
# -------------------------------------------------------------
unique_players = df[PLAYER_COL].dropna().unique()

for player in unique_players:
    safe_name = str(player).replace("/", "_").replace("\\", "_")
    pdf_path = os.path.join(PDF_OUTPUT_DIR, f"{safe_name}_SLJ_Classification.pdf")

    df_gen_L_p = df_gen_leg["L"][df_gen_leg["L"][PLAYER_COL] == player]
    df_abs_L_p = df_abs_leg["L"][df_abs_leg["L"][PLAYER_COL] == player]
    df_gen_R_p = df_gen_leg["R"][df_gen_leg["R"][PLAYER_COL] == player]
    df_abs_R_p = df_abs_leg["R"][df_abs_leg["R"][PLAYER_COL] == player]

    gen_value_cols_L = ["Generation_Class_L", "BW [KG]", "Jump Height (Imp-Mom) [cm] (L)"] + GENERATION_PARAMS["L"]
    abs_value_cols_L = ["Absorption_Class_L", "BW [KG]", "Jump Height (Imp-Mom) [cm] (L)"] + ABSORPTION_PARAMS["L"]
    gen_value_cols_R = ["Generation_Class_R", "BW [KG]", "Jump Height (Imp-Mom) [cm] (R)"] + GENERATION_PARAMS["R"]
    abs_value_cols_R = ["Absorption_Class_R", "BW [KG]", "Jump Height (Imp-Mom) [cm] (R)"] + ABSORPTION_PARAMS["R"]

    gen_class_map_L = {
        "Generation_Class_L": "Generation_Class_L",
        "BW [KG]": "BW [KG]_class",
        "Jump Height (Imp-Mom) [cm] (L)": "Jump Height (Imp-Mom) [cm] (L)_class",
        "Concentric Duration [ms] (L)": "Concentric Duration [ms] (L)_class",
        "Concentric Mean Force / BM [N/kg] (L)": "Concentric Mean Force / BM [N/kg] (L)_class",
    }
    abs_class_map_L = {
        "Absorption_Class_L": "Absorption_Class_L",
        "BW [KG]": "BW [KG]_class",
        "Jump Height (Imp-Mom) [cm] (L)": "Jump Height (Imp-Mom) [cm] (L)_class",
        "Braking Phase Duration [ms] (L)": "Braking Phase Duration [ms] (L)_class",
        "Countermovement Depth [cm] (L)": "Countermovement Depth [cm] (L)_class",
        "Eccentric Mean Force / BM [N/kg] (L)": "Eccentric Mean Force / BM [N/kg] (L)_class",
    }
    gen_class_map_R = {
        "Generation_Class_R": "Generation_Class_R",
        "BW [KG]": "BW [KG]_class",
        "Jump Height (Imp-Mom) [cm] (R)": "Jump Height (Imp-Mom) [cm] (R)_class",
        "Concentric Duration [ms] (R)": "Concentric Duration [ms] (R)_class",
        "Concentric Mean Force / BM [N/kg] (R)": "Concentric Mean Force / BM [N/kg] (R)_class",
    }
    abs_class_map_R = {
        "Absorption_Class_R": "Absorption_Class_R",
        "BW [KG]": "BW [KG]_class",
        "Jump Height (Imp-Mom) [cm] (R)": "Jump Height (Imp-Mom) [cm] (R)_class",
        "Braking Phase Duration [ms] (R)": "Braking Phase Duration [ms] (R)_class",
        "Countermovement Depth [cm] (R)": "Countermovement Depth [cm] (R)_class",
        "Eccentric Mean Force / BM [N/kg] (R)": "Eccentric Mean Force / BM [N/kg] (R)_class",
    }

    with PdfPages(pdf_path) as pdf:
        add_table_page(pdf, player, "SLJ Left - Generation", df_gen_L_p, gen_value_cols_L, gen_class_map_L)
        add_table_page(pdf, player, "SLJ Left - Absorption", df_abs_L_p, abs_value_cols_L, abs_class_map_L)
        add_table_page(pdf, player, "SLJ Right - Generation", df_gen_R_p, gen_value_cols_R, gen_class_map_R)
        add_table_page(pdf, player, "SLJ Right - Absorption", df_abs_R_p, abs_value_cols_R, abs_class_map_R)

    print(f"Saved player SLJ PDF: {pdf_path}")

with PdfPages(TEAM_PDF_PATH) as pdf:
    add_team_overview_leg(pdf, team_df_leg["L"], "Left", "L")
    add_team_overview_leg(pdf, team_df_leg["R"], "Right", "R")

print(f"Saved SLJ team overview PDF: {TEAM_PDF_PATH}")
