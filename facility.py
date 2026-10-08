"""
HSRP Facility Management App (CRUD + Dashboard)
Health System Resilience Project - Department of Health
Columns: Province | Name of Facility | Facility Type | Address | EMR | Accredited YAKAP with GAMOT | Accredited GAMOT package provider?

Run:
    python -m pip install streamlit pandas
    python -m streamlit run facility.py

Optional logos (put in the SAME folder as this file):
    logo.png              -> HSRP logo
    doh_logo.png          -> DOH seal
    bagong_pilipinas.png  -> Bagong Pilipinas logo
(.jpg / .jpeg also work)
"""

import base64
import html
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import altair as alt          # comes installed with streamlit
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).parent
DB_FILE = BASE_DIR / "facilities.db"

PROVINCES = [
    "Isabela", "Sorsogon", "Masbate", "Iloilo", "Leyte", "Bohol",
    "Misamis Oriental", "Lanao del Norte", "Zamboanga del Sur",
    "Zamboanga del Norte", "Maguindanao del Sur", "Maguindanao del Norte",
    "Agusan del Sur", "Davao de Oro", "Davao del Norte", "South Cotabato",
    "Sultan Kudarat","Zamboanga Sibugay"
]

# Edit this list to match the facility types you use
FACILITY_TYPES = [
    "Hospital", "Rural Health Unit (RHU)", "Barangay Health Station (BHS)",
    "City Health Office", "Provincial Health Office", "Other",
]


YAKAP_COL = "Accredited YAKAP with GAMOT"
GAMOT_COL = "Accredited GAMOT package provider?"
OWN_COL = "Ownership"
OWN_OPTIONS = ["", "P", "G"]
YN_OPTIONS = ["", "Yes", "No"]


def norm_yn(value):
    v = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip().lower()
    if v in ("yes", "y", "true", "1", "accredited"):
        return "Yes"
    if v in ("no", "n", "false", "0", "not accredited"):
        return "No"
    return ""


def norm_own(value):
    v = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip().lower()
    if v in ("p", "private"):
        return "P"
    if v in ("g", "government", "public", "govt"):
        return "G"
    return ""


def has_emr(value):
    """EMR is free text. Blank / 'No' / 'None' / 'N/A' count as no EMR."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip().lower() not in ("", "no", "none", "n/a", "na", "-", "not applicable", "no emr", "wala", "manual", "paper-based", "paper based")


# ---------- Colors (DOH billboard style) ----------
GREEN = "#5BB75B"
GREEN_DARK = "#3E9A3E"
BLUE = "#2E8FE8"
LINK = "#1D7FBF"
AMBER = "#F59E0B"
GRAY = "#CBD5E1"
DARK = "#1F2937"


# ---------- Logos ----------
def find_logo(stem):
    for ext in (".png", ".jpg", ".jpeg"):
        p = BASE_DIR / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def logo_uri(stem):
    p = find_logo(stem)
    if p is None:
        return None
    mime = "image/png" if p.suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


# ---------- Database ----------
def get_conn():
    return sqlite3.connect(DB_FILE)


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                province TEXT NOT NULL,
                name TEXT NOT NULL,
                facility_type TEXT,
                address TEXT,
                emr TEXT,
                yakap TEXT,
                gamot TEXT,
                ownership TEXT
            )
            """
        )
        # upgrade older databases that don't have the new columns yet
        cols = [r[1] for r in conn.execute("PRAGMA table_info(facilities)")]
        if "yakap" not in cols:
            conn.execute("ALTER TABLE facilities ADD COLUMN yakap TEXT")
        if "gamot" not in cols:
            conn.execute("ALTER TABLE facilities ADD COLUMN gamot TEXT")
        if "ownership" not in cols:
            conn.execute("ALTER TABLE facilities ADD COLUMN ownership TEXT")


def create_facility(province, name, ftype, address, emr, yakap="", gamot="", ownership=""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO facilities (province, name, facility_type, address, emr, yakap, gamot, ownership) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (province, name, ftype, address, emr, yakap, gamot, ownership),
        )


def read_facilities():
    with get_conn() as conn:
        return pd.read_sql_query(
            "SELECT id AS ID, province AS Province, name AS 'Name of Facility', "
            "facility_type AS 'Facility Type', address AS Address, emr AS 'Name of EMR', "
            f"COALESCE(yakap, '') AS '{YAKAP_COL}', "
            f"COALESCE(gamot, '') AS '{GAMOT_COL}', "
            f"COALESCE(ownership, '') AS '{OWN_COL}' "
            "FROM facilities ORDER BY province, name",
            conn,
        )


def update_facility(fid, province, name, ftype, address, emr, yakap="", gamot="", ownership=""):
    with get_conn() as conn:
        conn.execute(
            "UPDATE facilities SET province=?, name=?, facility_type=?, "
            "address=?, emr=?, yakap=?, gamot=?, ownership=? WHERE id=?",
            (province, name, ftype, address, emr, yakap, gamot, ownership, fid),
        )


def delete_facility(fid):
    with get_conn() as conn:
        conn.execute("DELETE FROM facilities WHERE id=?", (fid,))


def delete_many(ids):
    with get_conn() as conn:
        conn.executemany("DELETE FROM facilities WHERE id=?", [(int(i),) for i in ids])


def delete_all():
    with get_conn() as conn:
        conn.execute("DELETE FROM facilities")


# ---------- Styling ----------
CSS = f"""
<style>
:root {{ --green:{GREEN}; --blue:{BLUE}; --link:{LINK}; --dark:{DARK}; }}
""" + """
.block-container { padding-top: 3rem; max-width: 1300px; }
div[data-testid="stVerticalBlock"] { gap: .75rem; }
div[data-testid="stElementContainer"]:has(> .stMarkdown) { margin-bottom: -.35rem; }
#MainMenu, footer { visibility: hidden; }
html, body, [class*="css"] { font-family: Verdana, "Segoe UI", sans-serif; }

/* Header banner */
.app-header { background: var(--green); color: #fff; padding: 12px 24px;
  border-radius: 8px; display: flex; align-items: center; gap: 18px;
  position: relative; margin-bottom: 16px; }
.app-header .logos { display: flex; align-items: center; gap: 4px; flex: 0 0 auto; }
.app-header .brand { min-width: 0; }
.app-header img { height: 72px; width: auto; }
.app-header .small { font-size: .8rem; }
.app-header .dept { font-weight: 700; font-size: .95rem; margin-bottom: 2px; }
.app-header .title { font-size: 1.9rem; font-weight: 800; line-height: 1.15; }
.app-header .clock { position: absolute; top: 10px; right: 20px; font-size: .85rem; }

/* Left filter panel header */
.panel-head { background: var(--blue); color: #fff; font-weight: 700;
  padding: 7px 14px; border-radius: 6px 6px 0 0; font-size: .85rem; }
.page-title { font-size: 1.5rem; font-weight: 800; color: #E5E7EB;
  border-left: 6px solid var(--green); padding-left: 12px; margin: 4px 0 14px 0; }

/* KPI cards */
.kpi { background: #fff; border: 1px solid #E5E7EB; border-radius: 8px;
  padding: 14px 18px; border-left: 6px solid var(--c);
  box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.kpi .label { color: #6B7280; font-size: .72rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .04em; }
.kpi .value { color: var(--dark); font-size: 2rem; font-weight: 800; line-height: 1.2; }
.kpi .sub { color: #9CA3AF; font-size: .74rem; }

.section-title { font-weight: 700; color: inherit; font-size: 1rem; margin-bottom: 4px; }

/* Billboard-style table */
table.bb { width: 100%; border-collapse: collapse; font-size: .88rem; }
table.bb th { background: #F5F5F5; text-align: left; padding: 10px 12px;
  border: 1px solid #E5E7EB; color: var(--dark); }
table.bb td { padding: 10px 12px; border: 1px solid #E5E7EB; vertical-align: top; }
table.bb tr:nth-child(even) td { background: #F5F5F5; }
table.bb .lnk { color: var(--link); }
table.bb .meta { color: #6B7280; font-size: .78rem; margin-top: 2px; }
.badge { display: inline-block; padding: 3px 12px; border-radius: 4px;
  border: 1px solid #D1D5DB; background: #fff; font-size: .8rem; }
.badge.yes { border-color: var(--green); color: #2F7D32; background: #EEF8EE; }
.badge.no { color: #6B7280; }
</style>
"""


def esc(x):
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else html.escape(str(x))


def kpi(label, value, sub, color):
    return (
        f'<div class="kpi" style="--c:{color}"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div></div>'
    )


def section(title):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def render_header(page_label):
    manila = timezone(timedelta(hours=8))
    now = datetime.now(manila).strftime("%B %d, %Y %I:%M %p")
    imgs = "".join(
        f'<img src="{u}">'
        for u in (logo_uri("doh_logo"), logo_uri("bagong_pilipinas"), logo_uri("logo"))
        if u
    )
    st.markdown(
        f'<div class="app-header"><div class="logos">{imgs}</div><div class="brand">'
        f'<div class="small">Republic of the Philippines</div>'
        f'<div class="dept">Department of Health</div>'
        f'<div class="title">Health System Resilience Project (HSRP)</div>'
        f'</div><div class="clock">{now}</div></div>'
        f'<div class="page-title" style="color:#E5E7EB">{page_label}</div>',
        unsafe_allow_html=True,
    )


def recent_table(rows):
    head = f"<tr><th>Facility</th><th>Province</th><th>Facility Type</th><th>Name of EMR</th><th>{YAKAP_COL}</th><th>{GAMOT_COL}</th><th>{OWN_COL}</th></tr>"
    body = ""
    for _, r in rows.iterrows():
        badge = "yes" if has_emr(r["Name of EMR"]) else "no"
        body += (
            f'<tr><td><span class="lnk">{esc(r["Name of Facility"])}</span>'
            f'<div class="meta">{esc(r["Address"])}</div></td>'
            f'<td>{esc(r["Province"])}</td><td>{esc(r["Facility Type"])}</td>'
            f'<td><span class="badge {badge}">{esc(r["Name of EMR"]) or "-"}</span></td>'
            f'<td><span class="badge {"yes" if r[YAKAP_COL] == "Yes" else "no"}">{esc(r[YAKAP_COL]) or "-"}</span></td>'
            f'<td><span class="badge {"yes" if r[GAMOT_COL] == "Yes" else "no"}">{esc(r[GAMOT_COL]) or "-"}</span></td>'
            f'<td>{esc(r[OWN_COL]) or "-"}</td></tr>'
        )
    return f'<table class="bb">{head}{body}</table>'


def add_emr_columns(frame):
    """Add 'EMR System': the EMR name as typed, or 'No EMR'. Case variants are merged."""
    frame = frame.copy()
    frame["EMR System"] = frame["Name of EMR"].apply(lambda x: clean_text(x) if has_emr(x) else "No EMR")
    named = frame.loc[frame["EMR System"] != "No EMR", "EMR System"]
    if not named.empty:
        canon = named.groupby(named.str.lower()).agg(lambda x: x.value_counts().idxmax())
        frame["EMR System"] = frame["EMR System"].apply(
            lambda x: x if x == "No EMR" else canon.get(x.lower(), x)
        )
    return frame


# ---------- Dashboard ----------
def render_dashboard(df):
    df = add_emr_columns(df)
    systems = set(df["EMR System"])
    emr_options = sorted(systems - {"No EMR"}, key=str.lower) + (["No EMR"] if "No EMR" in systems else [])
    st.markdown('<div class="panel-head">Filter Facilities</div>', unsafe_allow_html=True)
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns(4)
        sel_prov = f1.multiselect("Province", PROVINCES, placeholder="All provinces")
        sel_type = f2.multiselect("Facility Type", FACILITY_TYPES, placeholder="All types")
        sel_emr = f3.multiselect("Name of EMR", emr_options, placeholder="All")
        search = f4.text_input("Facility name")
    right = st.container()

    data = df.copy()
    if sel_prov:
        data = data[data["Province"].isin(sel_prov)]
    if sel_type:
        data = data[data["Facility Type"].isin(sel_type)]
    if sel_emr:
        data = data[data["EMR System"].isin(sel_emr)]
    if search:
        data = data[data["Name of Facility"].str.contains(search, case=False, na=False)]

    with right:
        if df.empty:
            st.info("No data yet. Go to **Add Facility** or **Import / Export** to get started.")
            return
        if data.empty:
            st.warning("No records match the filters.")
            return

        data["EMR Status"] = data["EMR System"].apply(lambda x: "No EMR" if x == "No EMR" else "With EMR")
        total = len(data)
        with_emr = int((data["EMR Status"] == "With EMR").sum())
        without_emr = total - with_emr
        covered = data["Province"].nunique()
        rate = with_emr / total * 100

        # KPI cards
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(kpi("Total Facilities", total, "matching records", GREEN), unsafe_allow_html=True)
        k2.markdown(kpi("Provinces Covered", f"{covered}/{len(PROVINCES)}", "with at least 1 facility", BLUE), unsafe_allow_html=True)
        k3.markdown(kpi("With EMR", with_emr, f"{rate:.0f}% of facilities", GREEN_DARK), unsafe_allow_html=True)
        k4.markdown(kpi("Without EMR", without_emr, f"{100 - rate:.0f}% of facilities", AMBER), unsafe_allow_html=True)

        st.write("")

        # Donut + facility types
        c1, c2 = st.columns([1, 1.4])
        with c1:
            with st.container(border=True):
                section("EMR Adoption")
                donut_df = pd.DataFrame(
                    {"Status": ["With EMR", "No EMR"], "Count": [with_emr, without_emr]}
                )
                donut = (
                    alt.Chart(donut_df)
                    .mark_arc(innerRadius=55, outerRadius=90)
                    .encode(
                        theta="Count:Q",
                        color=alt.Color(
                            "Status:N",
                            scale=alt.Scale(domain=["With EMR", "No EMR"], range=[GREEN, GRAY]),
                            legend=alt.Legend(orient="bottom", title=None),
                        ),
                        tooltip=["Status", "Count"],
                    )
                    .properties(height=300)
                )
                st.altair_chart(donut)

        with c2:
            with st.container(border=True):
                section("Facilities by Type")
                type_df = data["Facility Type"].replace("", "Unspecified").value_counts().reset_index()
                type_df.columns = ["Type", "Count"]
                max_count = int(type_df["Count"].max())
                bars = (
                    alt.Chart(type_df)
                    .mark_bar(cornerRadiusEnd=5, color=BLUE)
                    .encode(
                        x=alt.X(
                            "Count:Q", title=None,
                            scale=alt.Scale(domain=[0, max_count * 1.15]),
                            axis=alt.Axis(tickMinStep=1, format="d"),
                        ),
                        y=alt.Y("Type:N", sort="-x", title=None),
                        tooltip=["Type", "Count"],
                    )
                )
                labels = bars.mark_text(align="left", dx=4).encode(text="Count:Q")
                st.altair_chart((bars + labels).properties(height=300))

        # EMR systems used
        with st.container(border=True):
            section("Facilities by Name of EMR")
            emr_df = data["EMR System"].value_counts().reset_index()
            emr_df.columns = ["System", "Count"]
            max_emr = int(emr_df["Count"].max())
            emr_bars = (
                alt.Chart(emr_df)
                .mark_bar(cornerRadiusEnd=5)
                .encode(
                    x=alt.X(
                        "Count:Q", title=None,
                        scale=alt.Scale(domain=[0, max_emr * 1.15]),
                        axis=alt.Axis(tickMinStep=1, format="d"),
                    ),
                    y=alt.Y("System:N", sort="-x", title=None),
                    color=alt.condition(
                        alt.datum.System == "No EMR", alt.value(GRAY), alt.value(GREEN)
                    ),
                    tooltip=["System", "Count"],
                )
            )
            emr_labels = emr_bars.mark_text(align="left", dx=4).encode(
                text="Count:Q", color=alt.value("#374151")
            )
            st.altair_chart((emr_bars + emr_labels).properties(height=max(120, 34 * len(emr_df))))

        # Facilities per province
        with st.container(border=True):
            section("Facilities per Province")
            prov_df = data.groupby(["Province", "EMR Status"]).size().reset_index(name="Count")
            stacked = (
                alt.Chart(prov_df)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Count:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d")),
                    y=alt.Y("Province:N", sort="-x", title=None),
                    color=alt.Color(
                        "EMR Status:N",
                        scale=alt.Scale(domain=["With EMR", "No EMR"], range=[GREEN, GRAY]),
                        legend=alt.Legend(orient="top", title=None),
                    ),
                    tooltip=["Province", "EMR Status", "Count"],
                )
                .properties(height=max(280, 26 * data["Province"].nunique()))
            )
            st.altair_chart(stacked)

        # Province summary
        with st.container(border=True):
            section("Province Summary")
            summary = (
                data.groupby("Province")
                .agg(Facilities=("ID", "count"),
                     With_EMR=("EMR Status", lambda s: (s == "With EMR").sum()))
                .reindex(sel_prov if sel_prov else PROVINCES)
                .fillna(0)
                .astype(int)
                .reset_index()
            )
            summary["EMR %"] = (
                summary["With_EMR"] / summary["Facilities"].replace(0, pd.NA) * 100
            ).fillna(0).astype(float)
            summary = summary.rename(columns={"With_EMR": "With EMR"})
            st.dataframe(
                summary,
                hide_index=True,
                column_config={
                    "EMR %": st.column_config.ProgressColumn(
                        "EMR %", min_value=0, max_value=100, format="%.0f%%"
                    )
                },
            )

        # Recently added (billboard style)
        with st.container(border=True):
            section("Recently Added Facilities")
            st.markdown(
                recent_table(data.sort_values("ID", ascending=False).head(10)),
                unsafe_allow_html=True,
            )


# ---------- Import helpers ----------
_PROV_BY_LOWER = {p.lower(): p for p in PROVINCES}
_PROV_LONGEST_FIRST = sorted(PROVINCES, key=len, reverse=True)


def clean_text(x):
    return "" if x is None else str(x).strip()


def norm(text):
    """Normalize a name for duplicate checks: ignore case, punctuation, extra spaces."""
    t = re.sub(r"[^a-z0-9 ]+", " ", clean_text(text).lower())
    return " ".join(t.split())


def detect_province(text):
    """Find one of the 17 province names inside any text (e.g. an address)."""
    t = clean_text(text).lower()
    for prov in _PROV_LONGEST_FIRST:
        if prov.lower() in t:
            return prov
    return None


def match_province(text):
    """Match a Province cell to the official list (ignores case, trailing commas)."""
    t = clean_text(text).strip(" ,.").lower()
    return _PROV_BY_LOWER.get(t) or detect_province(t)


# ---------- App ----------
_icon = find_logo("logo")
st.set_page_config(
    page_title="HSRP Facility Dashboard",
    page_icon=str(_icon) if _icon else "🏥",
    layout="wide",
)
st.markdown(CSS, unsafe_allow_html=True)
init_db()

page = st.sidebar.radio(
    "Menu", ["Dashboard", "View / Search", "Add Facility", "Edit / Delete", "Find Duplicates", "Import / Export"]
)

render_header(page)
df = read_facilities()

# ----- DASHBOARD -----
if page == "Dashboard":
    render_dashboard(df)

# ----- READ -----
elif page == "View / Search":
    st.subheader("All Facilities")
    f1, f2, f3 = st.columns(3)
    prov_filter = f1.multiselect("Province", PROVINCES)
    type_filter = f2.multiselect("Facility Type", FACILITY_TYPES)
    search = f3.text_input("Search name / address / EMR")

    view = df.copy()
    if prov_filter:
        view = view[view["Province"].isin(prov_filter)]
    if type_filter:
        view = view[view["Facility Type"].isin(type_filter)]
    if search:
        mask = view["Name of Facility"].str.contains(search, case=False, na=False) | \
               view["Address"].str.contains(search, case=False, na=False) | \
               view["Name of EMR"].str.contains(search, case=False, na=False)
        view = view[mask]

    st.caption(f"{len(view)} record(s)")
    st.dataframe(view, hide_index=True)

# ----- CREATE -----
elif page == "Add Facility":
    st.subheader("Add New Facility")
    with st.form("add_form", clear_on_submit=True):
        province = st.selectbox("Province", PROVINCES)
        name = st.text_input("Name of Facility")
        ftype = st.selectbox("Facility Type", FACILITY_TYPES)
        address = st.text_area("Address")
        emr = st.text_input("Name of EMR", placeholder="Type the EMR the facility uses (leave blank if none)")
        yakap = st.selectbox(YAKAP_COL, YN_OPTIONS)
        gamot = st.selectbox(GAMOT_COL, YN_OPTIONS)
        ownership = st.selectbox(OWN_COL, OWN_OPTIONS, help="P = Private, G = Government")
        submitted = st.form_submit_button("Save")

    if submitted:
        if not name.strip():
            st.error("Name of Facility is required.")
        else:
            create_facility(province, name.strip(), ftype, address.strip(), emr.strip(), yakap, gamot, ownership)
            st.success(f"Added: {name}")

# ----- UPDATE / DELETE -----
elif page == "Edit / Delete":
    st.subheader("Edit or Delete Facilities")

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)
    rnd = st.session_state.setdefault("del_round", 0)   # resets the delete widgets after a delete

    tab_edit, tab_del = st.tabs(["Edit one facility", "Delete (select many)"])

    # ---------- Edit one ----------
    with tab_edit:
        if df.empty:
            st.info("No records to edit.")
        else:
            labels = {
                row["ID"]: f'{row["Province"]} - {row["Name of Facility"]}'
                for _, row in df.iterrows()
            }
            fid = st.selectbox("Select facility", list(labels.keys()), format_func=lambda x: labels[x])
            rec = df[df["ID"] == fid].iloc[0]

            def idx(options, value):
                return options.index(value) if value in options else 0

            with st.form("edit_form"):
                province = st.selectbox("Province", PROVINCES, index=idx(PROVINCES, rec["Province"]))
                name = st.text_input("Name of Facility", rec["Name of Facility"])
                ftype = st.selectbox("Facility Type", FACILITY_TYPES, index=idx(FACILITY_TYPES, rec["Facility Type"]))
                address = st.text_area("Address", rec["Address"] or "")
                emr = st.text_input("Name of EMR", rec["Name of EMR"] or "")
                yakap = st.selectbox(YAKAP_COL, YN_OPTIONS, index=YN_OPTIONS.index(norm_yn(rec[YAKAP_COL])))
                gamot = st.selectbox(GAMOT_COL, YN_OPTIONS, index=YN_OPTIONS.index(norm_yn(rec[GAMOT_COL])))
                ownership = st.selectbox(OWN_COL, OWN_OPTIONS, index=OWN_OPTIONS.index(norm_own(rec[OWN_COL])), help="P = Private, G = Government")
                b1, b2 = st.columns(2)
                save = b1.form_submit_button("Update")
                remove = b2.form_submit_button("Delete this facility")

            if save:
                if not name.strip():
                    st.error("Name of Facility is required.")
                else:
                    update_facility(int(fid), province, name.strip(), ftype, address.strip(), emr.strip(), yakap, gamot, ownership)
                    st.session_state["flash"] = "Updated."
                    st.rerun()
            if remove:
                delete_facility(int(fid))
                st.session_state["flash"] = "Facility deleted."
                st.rerun()

    # ---------- Delete many ----------
    with tab_del:
        if df.empty:
            st.info("No records to delete.")
        else:
            st.caption("Tip: download a backup first (Import / Export > Download all records).")
            f1, f2, f3 = st.columns(3)
            prov_f = f1.multiselect("Province", PROVINCES, key="del_prov")
            type_f = f2.multiselect("Facility Type", FACILITY_TYPES, key="del_type")
            text_f = f3.text_input("Search name / address / EMR", key="del_text")

            shown = df.copy()
            if prov_f:
                shown = shown[shown["Province"].isin(prov_f)]
            if type_f:
                shown = shown[shown["Facility Type"].isin(type_f)]
            if text_f:
                shown = shown[
                    shown["Name of Facility"].str.contains(text_f, case=False, na=False)
                    | shown["Address"].str.contains(text_f, case=False, na=False)
                    | shown["Name of EMR"].str.contains(text_f, case=False, na=False)
                ]

            select_all = st.checkbox(f"Select all {len(shown)} record(s) shown", key=f"del_all_{rnd}")

            table = shown[["ID", "Province", "Name of Facility", "Facility Type", "Address", "Name of EMR", YAKAP_COL, GAMOT_COL, OWN_COL]].copy()
            table.insert(0, "Select", select_all)
            editor_key = f"del_editor_{rnd}_{select_all}_{hash(tuple(shown['ID'].tolist()))}"
            edited = st.data_editor(
                table,
                hide_index=True,
                key=editor_key,
                column_config={"Select": st.column_config.CheckboxColumn("Select")},
                disabled=[c for c in table.columns if c != "Select"],
            )
            chosen_ids = edited.loc[edited["Select"], "ID"].tolist()
            st.caption(f"{len(chosen_ids)} selected")

            confirm = st.checkbox(
                "I understand the selected records will be permanently deleted",
                key=f"del_confirm_{rnd}",
            )
            if st.button(f"Delete {len(chosen_ids)} selected", type="primary",
                         disabled=not chosen_ids or not confirm):
                delete_many(chosen_ids)
                st.session_state["flash"] = f"Deleted {len(chosen_ids)} record(s)."
                st.session_state["del_round"] = rnd + 1
                st.rerun()

            with st.expander("Danger zone: delete ALL records"):
                st.error(f"This permanently deletes all {len(df)} records in the database.")
                typed = st.text_input("Type DELETE ALL to confirm", key=f"del_all_text_{rnd}")
                if st.button("Delete ALL records", disabled=typed.strip() != "DELETE ALL"):
                    delete_all()
                    st.session_state["flash"] = "All records were deleted."
                    st.session_state["del_round"] = rnd + 1
                    st.rerun()

# ----- FIND DUPLICATES -----
elif page == "Find Duplicates":
    st.subheader("Find Duplicate Facilities")
    st.caption(
        "Duplicates = same facility name in the same province "
        "(capital letters, extra spaces and punctuation are ignored)."
    )
    if df.empty:
        st.info("No records yet.")
    else:
        tmp = df.copy()
        tmp["_key"] = tmp["Name of Facility"].apply(norm) + "|" + tmp["Province"].str.lower()
        dups = tmp[tmp.duplicated("_key", keep=False)].sort_values(["_key", "ID"])
        if dups.empty:
            st.success("No duplicates found.")
        else:
            extra_ids = tmp[tmp.duplicated("_key", keep="first")]["ID"].tolist()
            st.warning(
                f"{dups['_key'].nunique()} facility name(s) are duplicated "
                f"({len(extra_ids)} extra record(s))."
            )
            st.dataframe(dups.drop(columns=["_key"]), hide_index=True)
            st.caption("Cleaning keeps the oldest record (lowest ID) of each group and deletes the rest.")
            confirm = st.checkbox("I understand the extra records will be deleted")
            if st.button("Delete extra duplicates", disabled=not confirm):
                for fid in extra_ids:
                    delete_facility(int(fid))
                st.success(f"Deleted {len(extra_ids)} duplicate record(s). Refresh the page to update the list.")

# ----- IMPORT / EXPORT -----
elif page == "Import / Export":
    st.subheader("Import / Export")

    st.markdown("**Export**")
    x1, x2 = st.columns(2)
    x1.download_button(
        "Download all records (CSV)",
        df.drop(columns=["ID"]).to_csv(index=False).encode("utf-8"),
        "facilities.csv",
        "text/csv",
    )
    template = pd.DataFrame(
        columns=["Province", "Name of Facility", "Facility Type", "Address", "Name of EMR", YAKAP_COL, GAMOT_COL, OWN_COL]
    )
    x2.download_button(
        "Download blank template (CSV)",
        template.to_csv(index=False).encode("utf-8"),
        "facilities_template.csv",
        "text/csv",
    )

    st.markdown("---")
    st.markdown("**Import**")
    st.caption(
        "CSV or Excel. Only **Name of Facility** must be in the file. "
        "If there is no Province column, you can choose the province below."
    )
    up = st.file_uploader("Upload file", type=["csv", "xlsx", "xls"])

    if up is not None:
        try:
            raw = pd.read_csv(up) if up.name.lower().endswith(".csv") else pd.read_excel(up)
        except ImportError:
            st.error("To read Excel files, run: python -m pip install openpyxl")
            st.stop()
        except Exception as err:
            st.error(f"Could not read the file: {err}")
            st.stop()

        raw = raw.fillna("").astype(str)
        raw.columns = [str(c).strip() for c in raw.columns]
        cols = list(raw.columns)
        NONE = "(none)"
        options = [NONE] + cols

        def guess(keys, exclude=()):
            for col in cols:
                low = col.lower()
                if any(k in low for k in keys) and not any(x in low for x in exclude):
                    return col
            return NONE

        # Step 1: match columns
        st.markdown("**Step 1 - Match your file's columns**")
        m = st.columns(8)
        name_col = m[0].selectbox("Name of Facility", options, index=options.index(guess(("name", "facility"), ("type", "emr", "ehr"))))
        prov_col = m[1].selectbox("Province", options, index=options.index(guess(("province",))))
        type_col = m[2].selectbox("Facility Type", options, index=options.index(guess(("type",))))
        addr_col = m[3].selectbox("Address", options, index=options.index(guess(("address",))))
        emr_col = m[4].selectbox("Name of EMR", options, index=options.index(guess(("emr", "ehr"))))
        yakap_col = m[5].selectbox(YAKAP_COL, options, index=options.index(guess(("yakap",))))
        gamot_col = m[6].selectbox(GAMOT_COL, options, index=options.index(guess(("package", "provider"))))
        own_col = m[7].selectbox(OWN_COL, options, index=options.index(guess(("ownership", "owner"))))

        # Step 2: province
        st.markdown("**Step 2 - Province**")
        chosen = None
        detect = False
        if prov_col == NONE:
            st.info("No Province column in the file. Choose one province for ALL rows, or leave it and set the province row by row in Step 4.")
            pick = st.selectbox("Province for ALL rows in this file", ["(choose a province)"] + PROVINCES)
            chosen = pick if pick in PROVINCES else None
            detect = st.checkbox(
                "First try to detect the province from the Address and the Name of Facility",
                value=True,
            )
        else:
            pick = st.selectbox(
                "Use this province when a row's province is blank or not recognized",
                ["(none)"] + PROVINCES,
            )
            chosen = pick if pick in PROVINCES else None

        # Step 3: duplicates
        st.markdown("**Step 3 - If the facility is already in the database**")
        dup_mode = st.radio(
            "Same name + province:",
            ["Skip it", "Update the existing record (fills in Type / Address / EMR from this file)"],
            label_visibility="collapsed",
        )
        update_mode = dup_mode.startswith("Update")

        # Build the rows (province may still be empty)
        existing_map = {}
        for i, n, pv, o_t, o_a, o_e, o_y, o_g, o_o in zip(
            df["ID"], df["Name of Facility"], df["Province"],
            df["Facility Type"], df["Address"], df["Name of EMR"],
            df[YAKAP_COL], df[GAMOT_COL], df[OWN_COL],
        ):
            existing_map[(norm(n), clean_text(pv).lower())] = (int(i), n, o_t, o_a, o_e, o_y, o_g, o_o)

        base = []
        for row_no, (_, r) in enumerate(raw.iterrows()):
            name = clean_text(r[name_col]) if name_col != NONE else ""
            addr = clean_text(r[addr_col]) if addr_col != NONE else ""
            province = match_province(r[prov_col]) if prov_col != NONE else None
            if not province and detect:
                province = detect_province(f"{addr} {name}")
            if not province:
                province = chosen
            base.append({
                "File row": row_no + 2,   # row number in the user's file (row 1 = headers)
                "Province": province,
                "Name of Facility": name,
                "Facility Type": clean_text(r[type_col]) if type_col != NONE else "",
                "Address": addr,
                "Name of EMR": clean_text(r[emr_col]) if emr_col != NONE else "",
                YAKAP_COL: norm_yn(r[yakap_col]) if yakap_col != NONE else "",
                GAMOT_COL: norm_yn(r[gamot_col]) if gamot_col != NONE else "",
                OWN_COL: norm_own(r[own_col]) if own_col != NONE else "",
            })
        base_df = pd.DataFrame(base)

        # Step 4: set missing provinces row by row
        st.markdown("**Step 4 - Check the rows (you can set the Province of each row)**")
        n_blank = int(base_df["Province"].isna().sum())
        if n_blank:
            st.warning(
                f"{n_blank} row(s) have no province yet. Click the Province cell of each row and "
                "choose one, or pick a province for all rows in Step 2."
            )
        editor_key = (
            f"imp_editor_{up.name}_{hash(tuple(base_df['Province'].fillna('')))}"
            f"_{hash(tuple(base_df['Name of Facility']))}"
        )
        edited = st.data_editor(
            base_df,
            hide_index=True,
            key=editor_key,
            column_config={
                "Province": st.column_config.SelectboxColumn("Province", options=PROVINCES)
            },
            disabled=["File row", "Name of Facility", "Facility Type", "Address", "Name of EMR", YAKAP_COL, GAMOT_COL, OWN_COL],
        )

        # Check every row using the (possibly edited) province
        seen = set()
        records = []
        for _, r in edited.iterrows():
            name = clean_text(r["Name of Facility"])
            p_val = r["Province"]
            province = p_val if isinstance(p_val, str) and p_val in PROVINCES else None
            key = (norm(name), province.lower()) if province else None
            if not name:
                status = "Missing facility name"
            elif not province:
                status = "Province not set"
            elif key in seen:
                status = "Repeated in file"
            elif key in existing_map:
                status = "Already in database"
                seen.add(key)
            else:
                status = "OK"
                seen.add(key)
            records.append({
                "File row": int(r["File row"]),
                "Province": province or "",
                "Name of Facility": name,
                "Facility Type": clean_text(r["Facility Type"]),
                "Address": clean_text(r["Address"]),
                "Name of EMR": clean_text(r["Name of EMR"]),
                YAKAP_COL: norm_yn(r[YAKAP_COL]),
                GAMOT_COL: norm_yn(r[GAMOT_COL]),
                OWN_COL: norm_own(r[OWN_COL]),
                "Status": status,
            })

        prev = pd.DataFrame(records)
        count = lambda label: int((prev["Status"] == label).sum())
        n_ok = count("OK")
        n_exist = count("Already in database")
        n_rep = count("Repeated in file")
        n_prov = count("Province not set")
        n_name = count("Missing facility name")

        # Step 5: summary and import
        st.markdown("**Step 5 - Import**")
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("New", n_ok)
        s2.metric("Already in database", n_exist)
        s3.metric("Repeated in file", n_rep)
        s4.metric("Province not set", n_prov)
        s5.metric("Missing name", n_name)

        with st.expander("Status of each row", expanded=bool(n_prov or n_name)):
            st.dataframe(prev, hide_index=True)

        if n_prov:
            st.warning("Rows with no province are skipped. Set their province in the table above to include them.")

        to_do = n_ok + (n_exist if update_mode else 0)
        if st.button("Import", disabled=to_do == 0):
            updated = 0
            for rec in records:
                if rec["Status"] == "OK":
                    create_facility(
                        rec["Province"], rec["Name of Facility"], rec["Facility Type"],
                        rec["Address"], rec["Name of EMR"], rec[YAKAP_COL], rec[GAMOT_COL], rec[OWN_COL],
                    )
                elif rec["Status"] == "Already in database" and update_mode:
                    fid, o_name, o_t, o_a, o_e, o_y, o_g, o_o = existing_map[
                        (norm(rec["Name of Facility"]), rec["Province"].lower())
                    ]
                    update_facility(
                        fid, rec["Province"], o_name,
                        rec["Facility Type"] or o_t or "",
                        rec["Address"] or o_a or "",
                        rec["Name of EMR"] or o_e or "",
                        rec[YAKAP_COL] or o_y or "",
                        rec[GAMOT_COL] or o_g or "",
                        rec[OWN_COL] or o_o or "",
                    )
                    updated += 1
            msg = f"Added {n_ok} new facilities."
            if update_mode:
                msg += f" Updated {updated} existing."
            reasons = {
                "Already in database": "Already in database - skipped",
                "Repeated in file": "Repeated in the file - skipped",
                "Province not set": "No province",
                "Missing facility name": "No facility name",
            }
            handled = (prev["Status"] == "OK") | (
                (prev["Status"] == "Already in database") & update_mode
            )
            not_done = prev[~handled].copy()
            not_done["Reason not imported"] = not_done["Status"].map(reasons)
            st.session_state["import_report"] = {
                "msg": msg + " Open the Dashboard to see them.",
                "skipped": not_done.drop(columns=["Status"]),
            }

    # Report of the last import (stays visible, e.g. after downloading the CSV)
    report = st.session_state.get("import_report")
    if report:
        st.markdown("---")
        st.markdown("**Last import report**")
        st.success(report["msg"])
        skipped = report["skipped"]
        if skipped.empty:
            st.info("Every row in the file was imported or updated.")
        else:
            st.warning(f"{len(skipped)} row(s) were NOT imported:")
            st.dataframe(skipped, hide_index=True)
            st.download_button(
                "Download the not-imported rows (CSV)",
                skipped.to_csv(index=False).encode("utf-8"),
                "not_imported.csv",
                "text/csv",
            )
