"""IDRDH dashboard: read-only analytics on existing MotherDuck tables.

Use Streamlit secrets (MOTHERDUCK_TOKEN); this application never runs ETL or
creates/changes MotherDuck tables. Source tables are built by the IDRDH SQL notebook.
"""
from __future__ import annotations

import html
import math
import os
from datetime import datetime, timezone

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

DB = "idrdh_cloud"
SCHEMA = "main"
CURRENT_YEAR = datetime.now(timezone.utc).year
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
USGS = "idrdh_cloud.main.usgs_gempa_historis"
ERA5 = "idrdh_cloud.main.era5_historis_5_titik"
BNPB_JENIS = "idrdh_cloud.main.bnpb_hist_kejadian_jenis"
BNPB_PROV = "idrdh_cloud.main.bnpb_hist_kejadian_provinsi"
# Nearest reference place from the USGS text, e.g. "206 km E of Amahai, Indonesia" -> "Amahai, Indonesia".
LOKASI_SQL = r"TRIM(REGEXP_REPLACE(wilayah, '^(\d+\s*km\s+[A-Za-z]+\s+of\s+|[A-Za-z\s]+\s+of\s+)', ''))"
FONT = "Inter, system-ui, sans-serif"

st.set_page_config(
    page_title="IDRDH | Analitik Kebencanaan Indonesia",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


DARK = _is_dark()
PAL = (
    {"ink": "#e5e7eb", "muted": "#94a3b8", "line": "#2a3441", "card": "#151c27", "accent": "#818cf8", "soft": "#222a4d",
     "seq": ["#1e1b4b", "#4f46e5", "#c7d2fe"], "map": "carto-darkmatter"}
    if DARK else
    {"ink": "#0f172a", "muted": "#64748b", "line": "#e5e7eb", "card": "#ffffff", "accent": "#4f46e5", "soft": "#eef2ff",
     "seq": ["#eef2ff", "#818cf8", "#312e81"], "map": "carto-positron"}
)
CATEGORICAL = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#f97316", "#94a3b8"]
HEAT = ["#fbbf24", "#f97316", "#dc2626", "#7f1d1d"]

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, .stApp, button, input, textarea {font-family: 'Inter', system-ui, sans-serif;}
.block-container {padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1280px;}
header[data-testid="stHeader"] {background: transparent;}
#MainMenu, footer {visibility: hidden;}
h1, h2, h3, h4 {letter-spacing: -.02em; font-weight: 600;}
section[data-testid="stSidebar"] {border-right: 1px solid @LINE@;}

.hero {margin: 0 0 1.4rem;}
.eyebrow {font-size: .72rem; letter-spacing: .16em; text-transform: uppercase; color: @MUTED@; font-weight: 600;}
.hero h1 {font-size: 2.25rem; line-height: 1.15; margin: .4rem 0 .5rem; padding: 0; color: @INK@;}
.hero p {color: @MUTED@; max-width: 46rem; margin: 0 0 .95rem; font-size: .98rem; line-height: 1.55;}
.chips {display: flex; gap: .45rem; flex-wrap: wrap;}
.chip {font-size: .74rem; padding: .22rem .7rem; border: 1px solid @LINE@; border-radius: 999px; color: @MUTED@; background: @CARD@;}
.chip b {color: @INK@; font-weight: 600;}

.kpis, .insights {display: grid; gap: .9rem; margin: .5rem 0 1.1rem;}
.kpis {grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));}
.insights {grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));}
.kpi, .ins {background: @CARD@; border: 1px solid @LINE@; border-radius: 16px; padding: 1rem 1.15rem .85rem;
    transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;}
.kpi:hover, .ins:hover {transform: translateY(-2px); border-color: @ACCENT@; box-shadow: 0 10px 28px -16px @ACCENT@;}
.kpi .l, .ins .l {font-size: .76rem; color: @MUTED@; font-weight: 500;}
.ins .l {text-transform: uppercase; letter-spacing: .08em; font-size: .68rem; font-weight: 600; color: @ACCENT@;}
.kpi .v {font-size: 1.95rem; font-weight: 600; letter-spacing: -.03em; color: @INK@; line-height: 1.2; margin: .2rem 0 .35rem;}
.ins .v {font-size: 1.3rem; font-weight: 600; letter-spacing: -.02em; color: @INK@; line-height: 1.25; margin: .3rem 0 .3rem;}
.kpi .s {display: flex; justify-content: space-between; align-items: flex-end; min-height: 30px; gap: .5rem;}
.ins .d {font-size: .8rem; color: @MUTED@; line-height: 1.45;}
.delta {font-size: .72rem; font-weight: 600; padding: .14rem .55rem; border-radius: 999px; background: @SOFT@; color: @ACCENT@; white-space: nowrap;}

.sec {margin: .1rem 0 .4rem;}
.sec h4 {margin: 0; font-size: 1rem; font-weight: 600; color: @INK@; padding: 0;}
.sec p {margin: .15rem 0 0; font-size: .8rem; color: @MUTED@;}
.focus {display: inline-block; font-size: .8rem; padding: .3rem .8rem; border-radius: 999px; background: @SOFT@; color: @ACCENT@; font-weight: 600; margin-bottom: .5rem;}

div[data-baseweb="tab-list"] {gap: .35rem; border-bottom: 1px solid @LINE@;}
button[data-baseweb="tab"] {height: 2.7rem; padding: 0 .95rem; font-weight: 500;}
div[data-baseweb="tab-highlight"] {height: 2px;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 16px; border-color: @LINE@;}
details {border-radius: 12px !important; border-color: @LINE@ !important;}
div[data-testid="stCaptionContainer"] {color: @MUTED@;}
"""
for _k, _v in {"@INK@": PAL["ink"], "@MUTED@": PAL["muted"], "@LINE@": PAL["line"], "@CARD@": PAL["card"],
               "@ACCENT@": PAL["accent"], "@SOFT@": PAL["soft"]}.items():
    CSS = CSS.replace(_k, _v)
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def _read_token() -> str:
    """Get secret without writing it to code, logs or UI."""
    token = ""
    try:
        token = str(st.secrets["MOTHERDUCK_TOKEN"])
    except (KeyError, FileNotFoundError):
        token = os.environ.get("MOTHERDUCK_TOKEN", "")
    token = token.strip()
    if not token or token == "ISI_TOKEN_ANDA":
        raise RuntimeError("MOTHERDUCK_TOKEN belum dikonfigurasi di Streamlit Secrets.")
    return token


def connect():
    # The lowercase environment variable is documented by MotherDuck.
    os.environ["motherduck_token"] = _read_token()
    return duckdb.connect(f"md:{DB}")


@st.cache_data(ttl=600, show_spinner=False)
def sql_df(statement: str, params: tuple = ()) -> pd.DataFrame:
    """Small aggregated read-only SELECTs. Cache reduces repeated warehouse use."""
    with connect() as con:
        return con.execute(statement, list(params)).df()


@st.cache_data(ttl=600, show_spinner=False)
def available_tables() -> tuple[str, ...]:
    query = """
    SELECT table_name FROM information_schema.tables
    WHERE table_catalog = ? AND table_schema = ? AND table_type = 'BASE TABLE'
    ORDER BY table_name
    """
    with connect() as con:
        return tuple(con.execute(query, [DB, SCHEMA]).df()["table_name"].tolist())


def has(name: str, tables: set[str]) -> bool:
    return name in tables


def box_message(name: str):
    st.info(f"Tabel `{name}` belum tersedia di MotherDuck. Bagian ini akan muncul setelah tabel berhasil dibuat.")


# ---------- presentation helpers ----------
def heading(title: str, sub: str | None = None):
    note = f"<p>{sub}</p>" if sub else ""
    st.markdown(f'<div class="sec"><h4>{title}</h4>{note}</div>', unsafe_allow_html=True)


def panel(title: str, sub: str | None = None):
    """Bordered card with a heading; reopen with `with box:` to add content."""
    box = st.container(border=True)
    with box:
        heading(title, sub)
    return box


def style_fig(fig, height: int = 360, hover: str | None = None, bars: bool = False):
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=4, r=4, t=14, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=PAL["ink"], size=12), colorway=CATEGORICAL,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        hoverlabel=dict(bgcolor=PAL["card"], bordercolor=PAL["line"], font=dict(family=FONT, color=PAL["ink"])),
    )
    if hover:
        fig.update_layout(hovermode=hover)
    if bars:
        fig.update_layout(barcornerradius=5)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=PAL["line"], tickfont=dict(color=PAL["muted"]),
                     title_font=dict(color=PAL["muted"], size=12))
    fig.update_yaxes(gridcolor=PAL["line"], zeroline=False, showline=False, tickfont=dict(color=PAL["muted"]),
                     title_font=dict(color=PAL["muted"], size=12))
    return fig


def show_chart(fig, height: int = 360, hover: str | None = None, bars: bool = False,
               key: str | None = None, selectable: bool = False):
    style_fig(fig, height, hover, bars)
    return st.plotly_chart(fig, width="stretch", theme=None, key=key,
                           on_select="rerun" if selectable else "ignore", selection_mode="points")


def show_map(fig, height: int = 500):
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family=FONT, color=PAL["ink"]),
                      hoverlabel=dict(bgcolor=PAL["card"], bordercolor=PAL["line"], font=dict(color=PAL["ink"])))
    st.plotly_chart(fig, width="stretch", theme=None)


def show_table(df: pd.DataFrame):
    st.dataframe(df, width="stretch", hide_index=True)


def spark_svg(values: list[float]) -> str:
    vals = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(vals) < 2:
        return ""
    w, h, pad = 96, 30, 3
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pts = [(pad + i * (w - 2 * pad) / (len(vals) - 1), h - pad - (v - lo) / span * (h - 2 * pad)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline points="{line}" fill="none" '
            f'stroke="{PAL["accent"]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{PAL["accent"]}"/></svg>')


def kpi_card(label: str, value: str, delta: str | None = None, spark: list[float] | None = None) -> str:
    chip = f'<span class="delta">{html.escape(delta)}</span>' if delta else "<span></span>"
    return (f'<div class="kpi"><div class="l">{html.escape(label)}</div><div class="v">{html.escape(value)}</div>'
            f'<div class="s">{chip}{spark_svg(spark) if spark else ""}</div></div>')


def insight_card(tag: str, headline: str, detail: str) -> str:
    return (f'<div class="ins"><div class="l">{html.escape(tag)}</div><div class="v">{html.escape(headline)}</div>'
            f'<div class="d">{html.escape(detail)}</div></div>')


def year_control(min_year: int, max_year: int) -> tuple[int, int]:
    min_year, max_year = int(min_year), int(max_year)
    if min_year == max_year:
        st.sidebar.caption(f"Tahun yang tersedia: {min_year}")
        return min_year, max_year
    return st.sidebar.slider(
        "Periode gempa USGS", min_value=min_year, max_value=max_year,
        value=(min_year, max_year), step=1,
    )


def fmt_num(value: object, digits: int = 0) -> str:
    if value is None or pd.isna(value):
        return "—"
    if digits:
        return f"{float(value):,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{int(value):,}".replace(",", ".")


def days_in_year(year: int) -> int:
    year = int(year)
    return 366 if (year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)) else 365


def full_years(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only completed years with a valid value on every day."""
    mask = (df["hari_valid"] == df["tahun"].apply(days_in_year)) & (df["tahun"] < CURRENT_YEAR)
    return df[mask].copy()


def title_case(name: str) -> str:
    return str(name).title()


# ---------- connection ----------
try:
    tables = set(available_tables())
except Exception as exc:
    st.error("Koneksi ke MotherDuck belum berhasil. Periksa token, versi DuckDB, dan nama database `idrdh_cloud`.")
    st.caption(f"Jenis error: {type(exc).__name__}. Rincian rahasia tidak ditampilkan demi keamanan.")
    st.stop()

available_source = {
    "USGS historis": "usgs_gempa_historis",
    "BMKG M≥5 terbaru": "bmkg_gempaterkini",
    "BMKG gempa dirasakan": "bmkg_gempadirasakan",
    "BMKG gempa otomatis": "bmkg_autogempa",
    "BMKG prakiraan": "bmkg_prakiraan",
    "ERA5 sampel": "era5_historis_5_titik",
    "BNPB kejadian per jenis": "bnpb_hist_kejadian_jenis",
    "BNPB kejadian per provinsi": "bnpb_hist_kejadian_provinsi",
    "IRBI 2025": "irbi_provinsi_2025",
    "Status sumber": "status_sumber",
    "Kualitas data": "kualitas_data",
}
n_avail = sum(t in tables for t in available_source.values())

min_year, max_year, updated = 2010, CURRENT_YEAR, None
if has("usgs_gempa_historis", tables):
    try:
        rng = sql_df(f"SELECT MIN(tahun) AS awal, MAX(tahun) AS akhir, MAX(diambil_pada) AS upd FROM {USGS}")
        if not rng.empty and pd.notna(rng.iloc[0]["awal"]) and pd.notna(rng.iloc[0]["akhir"]):
            min_year = int(rng.iloc[0]["awal"])
            max_year = int(rng.iloc[0]["akhir"])
            updated = rng.iloc[0]["upd"]
    except Exception:
        pass

bnpb_range = "2010–2024"
if has("bnpb_hist_kejadian_jenis", tables):
    try:
        r = sql_df(f"SELECT MIN(tahun) AS a, MAX(tahun) AS b FROM {BNPB_JENIS}").iloc[0]
        bnpb_range = f"{int(r['a'])}–{int(r['b'])}"
    except Exception:
        pass

# ---------- sidebar ----------
st.sidebar.markdown("### Filter")
selected_years = year_control(min_year, max_year)
st.sidebar.caption("Periode berlaku untuk analisis gempa USGS.")
st.sidebar.divider()
if st.sidebar.button("Perbarui hasil query", width="stretch"):
    sql_df.clear()
    available_tables.clear()
    st.rerun()
st.sidebar.caption(f"Database `idrdh_cloud` · {n_avail}/{len(available_source)} tabel sumber tersedia")

if not tables:
    st.warning("Belum ditemukan tabel pada skema `idrdh_cloud.main`. Pastikan notebook SQL MotherDuck telah dijalankan.")
    st.stop()

# ---------- hero ----------
chips = [f"USGS <b>{min_year}–{max_year}</b>", f"BNPB <b>{bnpb_range}</b>", "ERA5 <b>5 titik sampel</b>"]
if updated is not None and pd.notna(updated):
    chips.append(f"Data diperbarui <b>{pd.to_datetime(updated):%d %b %Y}</b>")
st.markdown(
    f"""
    <div class="hero">
      <div class="eyebrow">IDRDH · Indonesia Disaster Resilience Data Hub</div>
      <h1>Analitik kebencanaan Indonesia</h1>
      <p>Gempa, cuaca, kejadian bencana, dan indeks risiko dalam satu tempat. Analisis bersifat deskriptif
      dan bukan sistem peringatan dini.</p>
      <div class="chips">{''.join(f'<span class="chip">{c}</span>' for c in chips)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# No mixing catalogs: USGS counts, BMKG feed and BNPB records are kept separate.
tab_overview, tab_gempa, tab_cuaca, tab_sumber, tab_kualitas = st.tabs(
    ["Ringkasan", "Gempa", "Cuaca", "BNPB & risiko", "Kualitas data"]
)

with tab_overview:
    st.caption("Statistik gempa dihitung hanya dari katalog USGS pada kotak geografis 95–141° BT, 11° LS–6° LU, M≥5; bukan seluruh bencana di Indonesia.")
    insights: list[str] = []
    annual = pd.DataFrame()

    if has("usgs_gempa_historis", tables):
        try:
            y1, y2 = selected_years
            x = sql_df(f"""
                SELECT COUNT(*) AS jumlah, MAX(magnitudo) AS m_maks,
                       ROUND(MEDIAN(kedalaman_km),1) AS kedalaman_median,
                       ROUND(COUNT(*) FILTER (WHERE kedalaman_km < 70) * 100.0
                             / NULLIF(COUNT(kedalaman_km),0), 1) AS persen_dangkal
                FROM {USGS}
                WHERE tahun BETWEEN ? AND ?
            """, selected_years).iloc[0]
            annual = sql_df(f"""
                SELECT tahun, COUNT(*) AS jumlah_gempa, MAX(magnitudo) AS m_maks,
                       MEDIAN(kedalaman_km) AS kedalaman_median,
                       COUNT(*) FILTER (WHERE kedalaman_km < 70) * 100.0 / NULLIF(COUNT(kedalaman_km),0) AS persen_dangkal
                FROM {USGS} WHERE tahun BETWEEN ? AND ? GROUP BY tahun ORDER BY tahun
            """, selected_years)

            delta = None
            span = y2 - y1 + 1
            if y1 - span >= min_year:
                prev = sql_df(f"SELECT COUNT(*) AS jumlah FROM {USGS} WHERE tahun BETWEEN ? AND ?",
                              (y1 - span, y1 - 1)).iloc[0]["jumlah"]
                if prev:
                    pct = (x["jumlah"] - prev) / prev * 100
                    delta = f"{'▲' if pct >= 0 else '▼'} {fmt_num(abs(pct), 1)}% vs {y1 - span}–{y1 - 1}"

            st.markdown(
                '<div class="kpis">'
                + kpi_card("Gempa USGS M≥5", fmt_num(x["jumlah"]), delta, annual["jumlah_gempa"].tolist())
                + kpi_card("Magnitudo maksimum", fmt_num(x["m_maks"], 1), None, annual["m_maks"].tolist())
                + kpi_card("Kedalaman median", f"{fmt_num(x['kedalaman_median'], 1)} km", None, annual["kedalaman_median"].tolist())
                + kpi_card("Gempa dangkal (<70 km)", f"{fmt_num(x['persen_dangkal'], 1)}%", None, annual["persen_dangkal"].tolist())
                + "</div>",
                unsafe_allow_html=True,
            )
            if y2 == CURRENT_YEAR:
                st.caption(f"Periode mencakup {CURRENT_YEAR} yang masih berjalan (YTD); perbandingan dengan periode sebelumnya dan titik terakhir sparkline dapat bias.")

            strongest = sql_df(f"""
                SELECT magnitudo, kedalaman_km, wilayah, timestamp_utc FROM {USGS}
                WHERE tahun BETWEEN ? AND ? ORDER BY magnitudo DESC, timestamp_utc LIMIT 1
            """, selected_years)
            if not strongest.empty:
                s = strongest.iloc[0]
                insights.append(insight_card(
                    "Gempa terkuat", f"M{fmt_num(s['magnitudo'], 1)}",
                    f"{str(s['timestamp_utc'])[:10]} · {s['wilayah']} · kedalaman {fmt_num(s['kedalaman_km'], 0)} km"))

            complete = annual[annual["tahun"] < CURRENT_YEAR]
            if not complete.empty:
                peak = complete.loc[complete["jumlah_gempa"].idxmax()]
                low = complete.loc[complete["jumlah_gempa"].idxmin()]
                insights.append(insight_card(
                    "Tahun teraktif", str(int(peak["tahun"])),
                    f"{fmt_num(peak['jumlah_gempa'])} kejadian · paling tenang {int(low['tahun'])} ({fmt_num(low['jumlah_gempa'])})"))

            top_loc = sql_df(f"""
                SELECT {LOKASI_SQL} AS lokasi, COUNT(*) AS jumlah FROM {USGS}
                WHERE tahun BETWEEN ? AND ? AND wilayah IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 1
            """, selected_years)
            if not top_loc.empty:
                insights.append(insight_card(
                    "Lokasi acuan teraktif", str(top_loc.iloc[0]["lokasi"]),
                    f"{fmt_num(top_loc.iloc[0]['jumlah'])} kejadian pada periode terpilih"))
            if pd.notna(x["persen_dangkal"]):
                insights.append(insight_card(
                    "Gempa dangkal", f"{fmt_num(x['persen_dangkal'], 1)}%",
                    "Kedalaman <70 km, kelas yang paling berpotensi merusak di permukaan"))
        except Exception:
            st.warning("Ringkasan USGS belum dapat dimuat. Periksa skema tabel.")
    else:
        box_message("usgs_gempa_historis")

    if has("bnpb_hist_kejadian_jenis", tables):
        try:
            jenis_total = sql_df(f"""
                SELECT wilayah_atau_jenis AS jenis, SUM(nilai) AS kejadian FROM {BNPB_JENIS}
                GROUP BY 1 ORDER BY 2 DESC
            """)
            if not jenis_total.empty:
                total = jenis_total["kejadian"].sum()
                top = jenis_total.iloc[0]
                top3 = jenis_total.head(3)["kejadian"].sum() / total * 100
                insights.append(insight_card(
                    "Bencana dominan (BNPB)", f"{title_case(top['jenis'])} · {fmt_num(top['kejadian'] / total * 100, 1)}%",
                    f"dari {fmt_num(total)} kejadian {bnpb_range}; tiga jenis teratas {fmt_num(top3, 1)}%"))
        except Exception:
            pass

    if insights:
        heading("Temuan utama", "Dihitung otomatis dari data pada filter periode; deskriptif, bukan prakiraan.")
        st.markdown(f'<div class="insights">{"".join(insights)}</div>', unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="medium")
    with left:
        if has("usgs_gempa_historis", tables) and not annual.empty:
            with panel("Gempa USGS per tahun", "Jumlah kejadian M≥5 pada periode terpilih"):
                fig = px.line(annual, x="tahun", y="jumlah_gempa", markers=True,
                              labels={"tahun": "Tahun", "jumlah_gempa": "Jumlah gempa"})
                fig.update_traces(line=dict(width=2.6), marker=dict(size=7), fill="tozeroy",
                                  fillcolor="rgba(99,102,241,.12)")
                show_chart(fig, 340, hover="x unified")
                if CURRENT_YEAR in annual["tahun"].tolist():
                    st.caption(f"{CURRENT_YEAR} masih berjalan (YTD); tidak setara dengan tahun lengkap.")
    with right:
        if has("bmkg_gempaterkini", tables):
            try:
                bmkg_latest = sql_df("""
                    SELECT timestamp_utc, magnitudo, kedalaman_km, wilayah, diambil_pada
                    FROM idrdh_cloud.main.bmkg_gempaterkini ORDER BY timestamp_utc DESC LIMIT 10
                """)
                taken = pd.to_datetime(bmkg_latest["diambil_pada"]).max()
                with panel("Gempa terbaru BMKG", f"Snapshot diunduh {taken:%d-%m-%Y %H:%M}; bukan total tahunan"):
                    show_table(bmkg_latest.drop(columns=["diambil_pada"]))
            except Exception:
                st.info("Tabel BMKG tersedia, tetapi struktur kolom perlu diperiksa.")

with tab_gempa:
    st.caption("Sumber: USGS Earthquake Catalog. Filter geografis mencakup sebagian kawasan sekitar Indonesia dan bukan batas administrasi negara.")
    if has("usgs_gempa_historis", tables):
        if "reset_n" not in st.session_state:
            st.session_state.reset_n = 0

        f1, f2 = st.columns([1, 2], gap="large")
        with f1:
            mag_min = st.slider("Magnitudo minimum", 5.0, 8.5, 5.0, 0.5)
        with f2:
            metric_choice = st.segmented_control(
                "Tren per tahun menampilkan", ["Kejadian", "Magnitudo maks", "Kedalaman median"],
                default="Kejadian", key="trend_metric") or "Kejadian"
        flt = (*selected_years, float(mag_min))
        try:
            trend = sql_df(f"""
                SELECT tahun, COUNT(*) AS kejadian, ROUND(MAX(magnitudo),1) AS m_maks,
                       ROUND(MEDIAN(kedalaman_km),1) AS kedalaman_median
                FROM {USGS} WHERE tahun BETWEEN ? AND ? AND magnitudo >= ?
                GROUP BY tahun ORDER BY tahun
            """, flt)
            heat = sql_df(f"""
                SELECT tahun, FLOOR(magnitudo * 2) / 2 AS kelas, COUNT(*) AS jumlah FROM {USGS}
                WHERE tahun BETWEEN ? AND ? AND magnitudo >= ? GROUP BY 1, 2 ORDER BY 1, 2
            """, flt)

            a, b = st.columns(2, gap="medium")
            focus: list[int] = []
            with a:
                box = panel("Tren per tahun", "Klik batang untuk memfokuskan peta, lokasi, dan tabel di bawah")
                with box:
                    if not trend.empty:
                        ycol = {"Kejadian": "kejadian", "Magnitudo maks": "m_maks", "Kedalaman median": "kedalaman_median"}[metric_choice]
                        fig = px.bar(trend, x="tahun", y=ycol, labels={"tahun": "Tahun", ycol: metric_choice})
                        prior = st.session_state.get(f"trend_{st.session_state.reset_n}")
                        picked = sorted({int(p["x"]) for p in (prior.selection.points if prior else [])})
                        if picked:
                            fig.update_traces(marker_color=[PAL["accent"] if int(t) in picked else PAL["line"] for t in trend["tahun"]])
                        event = show_chart(fig, 330, hover="x", bars=True,
                                           key=f"trend_{st.session_state.reset_n}", selectable=True)
                        focus = sorted({int(p["x"]) for p in event.selection.points}) if event else []
                    else:
                        st.info("Tidak ada kejadian pada filter ini.")
            with b:
                with panel("Heatmap tahun × magnitudo", "Intensitas jumlah kejadian per kelas 0,5"):
                    if not heat.empty:
                        pivot = heat.pivot(index="kelas", columns="tahun", values="jumlah").fillna(0).sort_index(ascending=False)
                        fig = px.imshow(pivot, aspect="auto", text_auto=True, color_continuous_scale=PAL["seq"],
                                        labels={"x": "Tahun", "y": "Magnitudo", "color": "Kejadian"})
                        fig.update_coloraxes(showscale=False)
                        show_chart(fig, 330)
                    else:
                        st.info("Tidak ada kejadian pada filter ini.")
            st.caption("Lonjakan satu tahun pada kelas besar bisa berasal dari satu rangkaian gempa utama dan susulannya, bukan tren naik jangka panjang.")

            if focus:
                fl, fr = st.columns([6, 1])
                label = str(focus[0]) if len(focus) == 1 else f"{focus[0]}–{focus[-1]}"
                fl.markdown(f'<span class="focus">Fokus tahun {label}</span>', unsafe_allow_html=True)
                if fr.button("Reset", key="reset_focus"):
                    st.session_state.reset_n += 1
                    st.rerun()
                ffl = (focus[0], focus[-1], float(mag_min))
            else:
                ffl = flt

            c, d = st.columns(2, gap="medium")
            with c:
                with panel("Kelas kedalaman", "Dangkal paling berpotensi merusak"):
                    depth = sql_df(f"""
                        SELECT CASE WHEN kedalaman_km < 70 THEN 'Dangkal (<70 km)'
                                    WHEN kedalaman_km < 300 THEN 'Menengah (70–300 km)'
                                    ELSE 'Dalam (>300 km)' END AS kelas, COUNT(*) AS jumlah
                        FROM {USGS}
                        WHERE tahun BETWEEN ? AND ? AND magnitudo >= ? AND kedalaman_km IS NOT NULL
                        GROUP BY 1
                    """, ffl)
                    if not depth.empty:
                        depth["persen"] = (depth["jumlah"] / depth["jumlah"].sum() * 100).round(1)
                        fig = px.pie(depth, names="kelas", values="jumlah", hole=0.62,
                                     category_orders={"kelas": ["Dangkal (<70 km)", "Menengah (70–300 km)", "Dalam (>300 km)"]},
                                     color_discrete_sequence=[PAL["accent"], "#a5b4fc", PAL["line"]])
                        fig.update_traces(textinfo="percent", sort=False, marker=dict(line=dict(color=PAL["card"], width=2)))
                        show_chart(fig, 320)
                    else:
                        st.info("Tidak ada data kedalaman.")
            with d:
                with panel("10 lokasi acuan teraktif", "Kota/pulau terdekat dari teks USGS"):
                    loc = sql_df(f"""
                        SELECT {LOKASI_SQL} AS lokasi, COUNT(*) AS kejadian, ROUND(MAX(magnitudo),1) AS m_maks
                        FROM {USGS}
                        WHERE tahun BETWEEN ? AND ? AND magnitudo >= ? AND wilayah IS NOT NULL
                        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
                    """, ffl)
                    if not loc.empty:
                        fig = px.bar(loc, x="kejadian", y="lokasi", orientation="h", hover_data=["m_maks"],
                                     labels={"kejadian": "Kejadian", "lokasi": "", "m_maks": "M maks"})
                        fig.update_layout(yaxis={"categoryorder": "total ascending"})
                        show_chart(fig, 320, bars=True)
                    else:
                        st.info("Tidak ada data lokasi.")

            e, g = st.columns(2, gap="medium")
            with e:
                with panel("Frekuensi–magnitudo (Gutenberg–Richter)", "Jumlah kejadian ≥ M dalam skala log"):
                    gr = sql_df(f"""
                        SELECT ROUND(magnitudo, 1) AS m, COUNT(*) AS n FROM {USGS}
                        WHERE tahun BETWEEN ? AND ? AND magnitudo >= ? GROUP BY 1 ORDER BY 1
                    """, ffl)
                    gr_stat = sql_df(f"""
                        SELECT COUNT(*) AS n, AVG(magnitudo) AS rata FROM {USGS}
                        WHERE tahun BETWEEN ? AND ? AND magnitudo >= ?
                    """, ffl).iloc[0]
                    if len(gr) >= 3:
                        gr["kumulatif"] = gr["n"][::-1].cumsum()[::-1]
                        fig = px.scatter(gr, x="m", y="kumulatif", log_y=True,
                                         labels={"m": "Magnitudo", "kumulatif": "Kejadian ≥ M"})
                        fig.update_traces(marker=dict(size=9))
                        show_chart(fig, 300, hover="closest")
                        b_value = math.log10(math.e) / (float(gr_stat["rata"]) - (float(mag_min) - 0.05))
                        st.caption(f"b-value (Aki–Utsu, Mc {fmt_num(mag_min, 1)}, n={fmt_num(gr_stat['n'])}): **{fmt_num(b_value, 2)}**. "
                                   "Sekitar 1 umum untuk gempa tektonik; sampel kecil membuat nilainya kurang stabil.")
                    else:
                        st.info("Data belum cukup untuk grafik ini.")
            with g:
                with panel("10 gempa terkuat", "Pada filter yang aktif"):
                    show_table(sql_df(f"""
                        SELECT timestamp_utc, magnitudo, kedalaman_km, wilayah FROM {USGS}
                        WHERE tahun BETWEEN ? AND ? AND magnitudo >= ?
                        ORDER BY magnitudo DESC, timestamp_utc DESC LIMIT 10
                    """, ffl))

            with panel("Peta episenter"):
                mode = st.segmented_control("Tampilan peta", ["Titik", "Kepadatan"], default="Titik", key="map_mode") or "Titik"
                limit = 1500 if mode == "Titik" else 20000
                geo = sql_df(f"""
                    SELECT timestamp_utc, latitude, longitude, magnitudo, kedalaman_km, wilayah
                    FROM {USGS}
                    WHERE tahun BETWEEN ? AND ? AND magnitudo >= ?
                      AND latitude IS NOT NULL AND longitude IS NOT NULL
                    ORDER BY timestamp_utc DESC LIMIT {limit}
                """, ffl)
                if not geo.empty:
                    if mode == "Titik":
                        fig = px.scatter_map(
                            geo, lat="latitude", lon="longitude", color="magnitudo", size="magnitudo",
                            size_max=14, zoom=3, hover_name="wilayah", color_continuous_scale=HEAT,
                            hover_data={"timestamp_utc": True, "magnitudo": True, "kedalaman_km": True,
                                        "latitude": False, "longitude": False},
                            map_style=PAL["map"],
                        )
                        st.caption("Maksimal 1.500 kejadian terbaru yang memenuhi filter; condong ke tahun-tahun terakhir bila tidak ada fokus tahun.")
                    else:
                        fig = px.density_map(geo, lat="latitude", lon="longitude", radius=12, zoom=3,
                                             color_continuous_scale=PAL["seq"], map_style=PAL["map"])
                        fig.update_coloraxes(showscale=False)
                        st.caption("Seluruh kejadian pada filter (maksimal 20.000); area lebih terang berarti lebih padat.")
                    show_map(fig, 500)
                else:
                    st.info("Tidak ada titik dengan koordinat valid pada periode ini.")
        except Exception:
            st.warning("Analisis gempa tidak dapat dibaca. Pastikan kolom USGS sesuai notebook SQL IDRDH.")
    else:
        box_message("usgs_gempa_historis")

with tab_cuaca:
    st.caption("Sumber: Open-Meteo ERA5, data reanalisis pada titik sampel, bukan data observasi BMKG seluruh provinsi.")
    if has("era5_historis_5_titik", tables):
        try:
            places = sql_df(f"""
                SELECT titik_sampel, MIN(tanggal) AS tanggal_awal, MAX(tanggal) AS tanggal_akhir,
                       COUNT(*) AS baris, COUNT(precipitation_sum) AS hari_hujan_valid
                FROM {ERA5} GROUP BY titik_sampel ORDER BY titik_sampel
            """)
            if places.empty:
                st.info("Tabel ERA5 ada, tetapi belum berisi data.")
            else:
                options = places["titik_sampel"].tolist()
                selected_places = st.pills("Titik sampel", options, selection_mode="multi", default=options, key="places")
                if not selected_places:
                    st.info("Pilih sedikitnya satu titik sampel.")
                else:
                    annual_w = sql_df(f"""
                        SELECT titik_sampel, tahun, COUNT(precipitation_sum) AS hari_valid,
                               ROUND(SUM(precipitation_sum),1) AS hujan_mm,
                               ROUND(AVG(temperature_2m_max),2) AS rerata_suhu_maks_c
                        FROM {ERA5} GROUP BY titik_sampel, tahun ORDER BY tahun, titik_sampel
                    """)
                    annual_w = annual_w[annual_w["titik_sampel"].isin(selected_places)]
                    annual_full = full_years(annual_w)

                    p1, p2 = st.columns(2, gap="medium")
                    with p1:
                        with panel("Pola musiman", "Rata-rata hujan per bulan"):
                            monthly = sql_df(f"""
                                WITH bulanan AS (
                                    SELECT titik_sampel, tahun, MONTH(tanggal) AS bulan,
                                           SUM(precipitation_sum) AS hujan_mm, COUNT(precipitation_sum) AS hari_valid,
                                           DAY(LAST_DAY(MIN(tanggal))) AS hari_bulan
                                    FROM {ERA5} GROUP BY 1, 2, 3
                                )
                                SELECT titik_sampel, bulan, ROUND(AVG(hujan_mm),1) AS rerata_hujan_mm
                                FROM bulanan WHERE hari_valid = hari_bulan GROUP BY 1, 2 ORDER BY 1, 2
                            """)
                            monthly = monthly[monthly["titik_sampel"].isin(selected_places)].copy()
                            if not monthly.empty:
                                monthly["nama_bulan"] = monthly["bulan"].apply(lambda m: BULAN[int(m) - 1])
                                fig = px.line(monthly, x="nama_bulan", y="rerata_hujan_mm", color="titik_sampel", markers=True,
                                              category_orders={"nama_bulan": BULAN},
                                              labels={"nama_bulan": "", "rerata_hujan_mm": "mm / bulan", "titik_sampel": "Titik"})
                                fig.update_traces(line=dict(width=2.4))
                                show_chart(fig, 340, hover="x unified")
                                notes = []
                                for place, grp in monthly.groupby("titik_sampel"):
                                    wet = grp.loc[grp["rerata_hujan_mm"].idxmax()]
                                    dry_m = grp.loc[grp["rerata_hujan_mm"].idxmin()]
                                    notes.append(f"**{place}**: terbasah {BULAN[int(wet['bulan']) - 1]} ({fmt_num(wet['rerata_hujan_mm'], 0)} mm), "
                                                 f"terkering {BULAN[int(dry_m['bulan']) - 1]} ({fmt_num(dry_m['rerata_hujan_mm'], 0)} mm)")
                                st.caption("  \n".join(notes) + "  \nHanya bulan dengan data harian lengkap yang dihitung.")
                    with p2:
                        with panel("Anomali hujan tahunan", "Selisih dari rata-rata tiap titik"):
                            if annual_full.empty:
                                st.info("Belum ada tahun dengan cakupan harian lengkap.")
                            else:
                                annual_full["anomali_persen"] = annual_full.groupby("titik_sampel")["hujan_mm"].transform(
                                    lambda s: (s - s.mean()) / s.mean() * 100).round(1)
                                fig = px.bar(annual_full, x="tahun", y="anomali_persen", color="titik_sampel", barmode="group",
                                             labels={"tahun": "", "anomali_persen": "% dari rata-rata", "titik_sampel": "Titik"})
                                show_chart(fig, 340, hover="x unified", bars=True)
                                st.caption("Positif = lebih basah dari rata-rata titik; negatif = lebih kering. Dashboard tidak menguji kaitan dengan ENSO.")

                    p3, p4 = st.columns(2, gap="medium")
                    with p3:
                        with panel("Hari hujan ekstrem", "Jumlah hari melewati ambang per tahun lengkap"):
                            thr = st.segmented_control("Ambang hujan harian", ["20 mm", "50 mm", "100 mm"],
                                                       default="50 mm", key="thr") or "50 mm"
                            thr_v = float(thr.split()[0])
                            extreme = sql_df(f"""
                                SELECT titik_sampel, tahun, COUNT(precipitation_sum) AS hari_valid,
                                       COUNT(*) FILTER (WHERE precipitation_sum >= ?) AS hari_ekstrem
                                FROM {ERA5} GROUP BY 1, 2 ORDER BY 2, 1
                            """, (thr_v,))
                            extreme = full_years(extreme[extreme["titik_sampel"].isin(selected_places)])
                            if not extreme.empty:
                                fig = px.bar(extreme, x="tahun", y="hari_ekstrem", color="titik_sampel", barmode="group",
                                             labels={"tahun": "", "hari_ekstrem": f"hari ≥ {thr}", "titik_sampel": "Titik"})
                                show_chart(fig, 300, hover="x unified", bars=True)
                                tot = extreme.groupby("titik_sampel")["hari_ekstrem"].sum().sort_values(ascending=False)
                                st.caption("Total: " + ", ".join(f"{k} {int(v)}" for k, v in tot.items()) +
                                           ". Proksi hujan lebat di titik sampel, bukan kejadian banjir.")
                            else:
                                st.info("Belum ada tahun lengkap.")
                    with p4:
                        with panel("Periode kering terpanjang", "Hari berturut-turut dengan hujan <1 mm"):
                            dry = sql_df(f"""
                                WITH d AS (
                                    SELECT titik_sampel, tahun, tanggal, precipitation_sum < 1 AS kering,
                                           tanggal - CAST(ROW_NUMBER() OVER (
                                               PARTITION BY titik_sampel, tahun, (precipitation_sum < 1)
                                               ORDER BY tanggal) AS INTEGER) AS grup
                                    FROM {ERA5} WHERE precipitation_sum IS NOT NULL
                                ),
                                runs AS (
                                    SELECT titik_sampel, tahun, COUNT(*) AS panjang
                                    FROM d WHERE kering GROUP BY titik_sampel, tahun, grup
                                )
                                SELECT titik_sampel, tahun, MAX(panjang) AS hari_kering_terpanjang
                                FROM runs GROUP BY 1, 2 ORDER BY 2, 1
                            """)
                            dry = dry[dry["titik_sampel"].isin(selected_places)]
                            dry = dry.merge(annual_w[["titik_sampel", "tahun", "hari_valid"]], on=["titik_sampel", "tahun"])
                            dry = full_years(dry)
                            if not dry.empty:
                                fig = px.line(dry, x="tahun", y="hari_kering_terpanjang", color="titik_sampel", markers=True,
                                              labels={"tahun": "", "hari_kering_terpanjang": "hari", "titik_sampel": "Titik"})
                                fig.update_traces(line=dict(width=2.4))
                                show_chart(fig, 340, hover="x unified")
                                st.caption("Proksi kekeringan meteorologis pada titik sampel.")
                            else:
                                st.info("Belum ada tahun lengkap.")

                    with st.expander("Tabel ringkasan dan cakupan data"):
                        show_table(annual_w)
                        show_table(places)
        except Exception:
            st.warning("Tabel ERA5 tidak dapat dibaca; periksa hasil cleaning dan nama kolom.")
    elif has("era5_raw_5_titik", tables):
        st.info("Tersedia tabel mentah `era5_raw_5_titik`, tetapi tabel hasil cleaning `era5_historis_5_titik` belum dibuat. Jalankan bagian cleaning pada SQL Notebook.")
    else:
        box_message("era5_historis_5_titik")

with tab_sumber:
    st.caption(f"Sumber: BNPB Satu Data (rekap historis {bnpb_range}). Korban meninggal dan kejadian 2025 belum berhasil dimuat; lihat tab Kualitas data.")

    if has("bnpb_hist_kejadian_jenis", tables):
        try:
            jenis_year = sql_df(f"""
                SELECT tahun, wilayah_atau_jenis AS jenis, nilai AS kejadian FROM {BNPB_JENIS} ORDER BY tahun
            """)
            jenis_year["jenis"] = jenis_year["jenis"].apply(title_case)
            order = jenis_year.groupby("jenis")["kejadian"].sum().sort_values(ascending=False).index.tolist()

            with panel("Kejadian bencana per tahun", "Saring jenis bencana dan pilih tampilan jumlah atau proporsi"):
                g1, g2 = st.columns([3, 1], gap="large")
                with g1:
                    chosen = st.pills("Jenis bencana", order, selection_mode="multi", default=order, key="jenis")
                with g2:
                    view = st.segmented_control("Tampilan", ["Jumlah", "Proporsi"], default="Jumlah", key="jenis_view") or "Jumlah"
                if chosen:
                    shown = jenis_year[jenis_year["jenis"].isin(chosen)]
                    fig = px.bar(shown, x="tahun", y="kejadian", color="jenis", category_orders={"jenis": order},
                                 labels={"tahun": "", "kejadian": "Proporsi (%)" if view == "Proporsi" else "Kejadian", "jenis": "Jenis"})
                    if view == "Proporsi":
                        fig.update_layout(barnorm="percent")
                    show_chart(fig, 400, hover="x unified", bars=True)
                    yearly = shown.groupby("tahun")["kejadian"].sum()
                    hydromet = jenis_year[jenis_year["jenis"].isin(["Banjir", "Cuaca Ekstrem", "Tanah Longsor"])]["kejadian"].sum()
                    st.caption(
                        f"Puncak {int(yearly.idxmax())} ({fmt_num(yearly.max())} kejadian pada jenis terpilih); "
                        f"bencana hidrometeorologi (banjir, cuaca ekstrem, tanah longsor) = {fmt_num(hydromet / jenis_year['kejadian'].sum() * 100, 1)}% seluruh kejadian. "
                        "Kenaikan jumlah dapat berasal dari pelaporan yang makin lengkap, bukan hanya bencana yang makin sering.")
                else:
                    st.info("Pilih sedikitnya satu jenis bencana.")

            ind_tables = {
                "Terdampak": "bnpb_hist_terdampak", "Mengungsi": "bnpb_hist_mengungsi", "Luka-luka": "bnpb_hist_luka",
                "Hilang": "bnpb_hist_hilang", "Rumah rusak": "bnpb_hist_rumah_rusak",
            }
            ind_ok = {k: v for k, v in ind_tables.items() if v in tables}
            if ind_ok:
                with panel("Dampak menurut jenis bencana", "Pilih indikator dampak"):
                    choice = st.pills("Indikator", list(ind_ok), selection_mode="single", default=list(ind_ok)[0], key="indikator") or list(ind_ok)[0]
                    impact = sql_df(f"""
                        SELECT wilayah_atau_jenis AS jenis, SUM(nilai) AS total
                        FROM idrdh_cloud.main.{ind_ok[choice]} WHERE granularitas = 'jenis_bencana'
                        GROUP BY 1 ORDER BY 2 DESC
                    """)
                    impact["jenis"] = impact["jenis"].apply(title_case)
                    if not impact.empty:
                        unit = "unit" if choice == "Rumah rusak" else "orang"
                        fig = px.bar(impact, x="total", y="jenis", orientation="h", labels={"total": f"{choice} ({unit})", "jenis": ""})
                        fig.update_traces(marker_color=[PAL["accent"] if i == 0 else PAL["line"] for i in range(len(impact))])
                        fig.update_layout(yaxis={"categoryorder": "total ascending"})
                        show_chart(fig, 340, bars=True)
                        lead = impact.iloc[0]
                        st.caption(f"{lead['jenis']} menyumbang {fmt_num(lead['total'] / impact['total'].sum() * 100, 1)}% dari total {choice.lower()}. "
                                   "Jumlah tahun tercatat bisa berbeda antar jenis; korban meninggal tidak tersedia.")
        except Exception:
            st.warning("Data kejadian BNPB per jenis belum dapat ditampilkan.")
    else:
        box_message("bnpb_hist_kejadian_jenis")

    prov_events = pd.DataFrame()
    if has("bnpb_hist_kejadian_provinsi", tables):
        try:
            prov_events = sql_df(f"""
                SELECT wilayah_atau_jenis AS provinsi, SUM(nilai) AS kejadian FROM {BNPB_PROV}
                GROUP BY 1 ORDER BY 2 DESC
            """)
        except Exception:
            st.warning("Data kejadian BNPB per provinsi belum dapat ditampilkan.")
    else:
        box_message("bnpb_hist_kejadian_provinsi")

    irbi_name = next((n for n in ("irbi_provinsi_2025", "irbi_provinsi_2025_validated") if n in tables), None)
    col_l, col_r = st.columns(2, gap="medium")
    with col_l:
        if not prov_events.empty:
            with panel("Provinsi dengan kejadian terbanyak", f"10 teratas, {bnpb_range}"):
                top10 = prov_events.head(10).copy()
                top10["provinsi"] = top10["provinsi"].apply(title_case)
                fig = px.bar(top10, x="kejadian", y="provinsi", orientation="h", labels={"kejadian": "Kejadian", "provinsi": ""})
                fig.update_traces(marker_color=[PAL["accent"] if i < 3 else PAL["line"] for i in range(len(top10))])
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                show_chart(fig, 400, bars=True)
                share3 = prov_events.head(3)["kejadian"].sum() / prov_events["kejadian"].sum() * 100
                st.caption(f"Tiga provinsi teratas = {fmt_num(share3, 1)}% seluruh kejadian. Jumlah dipengaruhi luas wilayah, penduduk, dan cara pelaporan, bukan ukuran risiko.")
    with col_r:
        if irbi_name:
            try:
                irbi = sql_df(f"""
                    SELECT provinsi, indeks_risiko, sumber FROM idrdh_cloud.main.{irbi_name}
                    WHERE indeks_risiko IS NOT NULL ORDER BY indeks_risiko DESC
                """)
                q1, q2 = irbi["indeks_risiko"].quantile([1 / 3, 2 / 3])
                irbi["kelompok_relatif"] = irbi["indeks_risiko"].apply(
                    lambda v: "Tinggi" if v > q2 else ("Sedang" if v > q1 else "Rendah"))
                with panel("Indeks Risiko Bencana (IRBI) 2025", "15 provinsi dengan skor tertinggi"):
                    top = irbi.head(15).copy()
                    top["provinsi"] = top["provinsi"].apply(title_case)
                    fig = px.bar(top, x="indeks_risiko", y="provinsi", orientation="h", color="kelompok_relatif",
                                 color_discrete_map={"Tinggi": PAL["accent"], "Sedang": "#a5b4fc", "Rendah": PAL["line"]},
                                 labels={"indeks_risiko": "Skor IRBI", "provinsi": "", "kelompok_relatif": "Kelompok"})
                    fig.update_layout(yaxis={"categoryorder": "total ascending"})
                    show_chart(fig, 400, bars=True)
                    st.caption(f"Sumber: {irbi['sumber'].iloc[0]}. Kelompok adalah tertil relatif antar provinsi, bukan kelas risiko resmi BNPB.")
            except Exception:
                irbi = pd.DataFrame()
                st.warning("Skema tabel IRBI belum sesuai.")
        elif has("irbi_provinsi_2025_calon", tables):
            st.warning("Ekstraksi IRBI masih berstatus calon; jangan dipakai sebagai peringkat resmi sebelum diverifikasi.")
        else:
            box_message("irbi_provinsi_2025")

    if irbi_name and not prov_events.empty and "irbi" in locals() and not irbi.empty:
        merged = irbi.merge(prov_events, on="provinsi", how="inner")
        if len(merged) >= 5:
            with panel("Skor risiko vs jumlah kejadian", "Setiap titik adalah satu provinsi; arahkan kursor untuk nama"):
                merged["label"] = merged["provinsi"].apply(title_case)
                fig = px.scatter(merged, x="indeks_risiko", y="kejadian", hover_name="label", color="kelompok_relatif",
                                 color_discrete_map={"Tinggi": PAL["accent"], "Sedang": "#a5b4fc", "Rendah": PAL["muted"]},
                                 labels={"indeks_risiko": "Skor IRBI 2025", "kejadian": f"Kejadian BNPB {bnpb_range}", "kelompok_relatif": "Kelompok"})
                fig.update_traces(marker=dict(size=11, line=dict(color=PAL["card"], width=1.5)))
                show_chart(fig, 400, hover="closest")
                rho = merged["indeks_risiko"].rank().corr(merged["kejadian"].rank())
                unmatched = len(irbi) - len(merged)
                kuat = "lemah" if abs(rho) < 0.3 else ("sedang" if abs(rho) < 0.6 else "kuat")
                st.caption(f"Korelasi peringkat (Spearman) = **{fmt_num(rho, 2)}** ({kuat}) pada {len(merged)} provinsi"
                           + (f"; {unmatched} provinsi tidak cocok namanya dan dikeluarkan." if unmatched else ".")
                           + " IRBI menggabungkan ancaman, kerentanan, dan kapasitas, jadi tidak harus selaras dengan jumlah kejadian. Korelasi bukan sebab-akibat.")
            with st.expander("Tabel IRBI lengkap"):
                show_table(irbi.drop(columns=["sumber"]))

with tab_kualitas:
    st.caption("Status menunjukkan tabel yang benar-benar tersedia; bukan klaim bahwa seluruh sumber telah lengkap.")
    k1, k2 = st.columns([2, 3], gap="medium")
    with k1:
        with panel("Ketersediaan tabel", f"{n_avail} dari {len(available_source)} tersedia"):
            show_table(pd.DataFrame([
                {"Sumber": label, "Status": "✅ Tersedia" if table in tables else "⛔ Belum tersedia"}
                for label, table in available_source.items()
            ]))
    with k2:
        if has("status_sumber", tables):
            try:
                status = sql_df("""
                    SELECT dataset, status, rows AS baris, coverage AS cakupan, message AS catatan
                    FROM idrdh_cloud.main.status_sumber
                    ORDER BY CASE WHEN status = 'OK' THEN 1 ELSE 0 END, dataset
                """)
                bad = status[status["status"] != "OK"]
                with panel("Status pengambilan sumber", f"{len(bad)} sumber belum OK (di urutan teratas)"):
                    show_table(status)
            except Exception:
                st.info("Tabel status_sumber ada, tetapi strukturnya berbeda.")
    if has("kualitas_data", tables):
        try:
            with panel("Laporan kualitas hasil ETL"):
                show_table(sql_df("""
                    SELECT dataset, baris, tanggal_kosong, duplikat_kunci, tahun_awal, tahun_akhir
                    FROM idrdh_cloud.main.kualitas_data
                """))
        except Exception:
            st.warning("Tabel kualitas_data ada tetapi strukturnya berbeda.")
    with st.expander("Seluruh tabel dalam database"):
        show_table(pd.DataFrame({"table_name": sorted(tables)}))

st.divider()
st.caption(
    "Sumber: USGS Earthquake Catalog, BMKG Open Data, Open-Meteo/ERA5, BNPB Satu Data, BNPB/InaRISK (IRBI). "
    "Analisis bersifat deskriptif; bukan prakiraan, peringatan dini, atau indeks risiko baru. "
    "Dashboard membaca snapshot yang telah diunggah ke MotherDuck."
)
