"""Оформление сайта: стили, шапка страницы, карточки показателей, блоки формул."""
import html

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700&family=Literata:opsz,wght@7..72,500;7..72,600;7..72,700&display=swap');
:root{
  --serif:'Literata', Georgia, serif; --sans:'Golos Text', 'Segoe UI', sans-serif;
  --bg:#F6F8FA; --card:#FFFFFF; --text:#182522; --muted:#66756F; --green:#167D61;
  --green-soft:#E8F4EE; --border:#E2E9E5; --amber:#B7791F; --amber-soft:#FBF3E4;
}
/* Общая сетка и фон */
.stApp{background:var(--bg);}
.block-container{padding-top:1.6rem; padding-bottom:3rem; max-width:1320px;}
header[data-testid="stHeader"]{background:transparent;}
/* Заголовки: спокойная иерархия */
h1,h2,h3,h4{font-family:var(--serif) !important; color:var(--text); letter-spacing:-.005em;}
h1{font-size:1.9rem !important; font-weight:700 !important;}
h2{font-size:1.3rem !important; font-weight:600 !important; margin-top:.6rem !important;}
h3,h4{font-size:1.1rem !important; font-weight:600 !important;}
p, li, label, .stMarkdown{color:var(--text);}
[data-testid="stCaptionContainer"]{color:var(--muted) !important; font-size:.86rem;}
/* Боковое меню */
section[data-testid="stSidebar"]{background:#FFFFFF; border-right:1px solid var(--border);}
[data-testid="stSidebarNav"] a{border-radius:10px;}
[data-testid="stSidebarNav"] a[aria-current="page"]{background:var(--green-soft);}
[data-testid="stSidebarNav"] a[aria-current="page"] span{color:var(--green) !important; font-weight:600;}
[data-testid="stNavSectionHeader"]{color:var(--muted) !important; font-size:.72rem !important;
  letter-spacing:.08em; text-transform:uppercase; font-weight:600;}
/* Панели с рамкой */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]){border-radius:16px;}
div[data-testid="stVerticalBlockBorderWrapper"][data-test-border="true"],
div[data-testid="stVerticalBlockBorderWrapper"]>div[style*="border"]{background:var(--card);}
.stButton>button, .stDownloadButton>button{border-radius:10px; font-weight:600;}
.stButton>button[kind="primary"]{box-shadow:0 1px 2px rgba(22,125,97,.25);}
[data-testid="stExpander"] details{border-radius:12px; background:var(--card); border-color:var(--border);}
[data-testid="stDataFrame"]{border-radius:12px; overflow:hidden;}
[data-testid="stImage"] img{border-radius:12px;}
iframe{border-radius:12px;}
/* Шапка страницы */
.ea-head{display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin:0 0 18px 0;}
.ea-eyebrow{font-size:.85rem; color:var(--muted); margin-bottom:2px;}
.ea-eyebrow::after{content:" /"; color:#B9C4BF;}
.ea-title{font-family:var(--serif); font-size:2.05rem !important; font-weight:700; color:var(--text); line-height:1.15; margin:0;}
.ea-sub{color:var(--muted); font-size:.98rem; margin-top:8px; max-width:760px; line-height:1.5;}
.ea-pill{display:inline-flex; align-items:center; gap:7px; white-space:nowrap; padding:6px 12px; border-radius:999px;
  font-size:.82rem; font-weight:600; background:var(--green-soft); color:var(--green); border:1px solid #CFE7DB;}
.ea-pill.wait{background:#F1F3F2; color:var(--muted); border-color:var(--border);}
.ea-pill.warn{background:var(--amber-soft); color:var(--amber); border-color:#F0DDB8;}
.ea-dot{width:8px; height:8px; border-radius:50%; background:currentColor;}
/* Карточки показателей */
.ea-kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:6px 0 18px 0;}
.ea-kpi{background:var(--card); border:1px solid var(--border); border-radius:14px; padding:14px 16px;}
.ea-kpi .l{font-size:.8rem; color:var(--muted); margin-bottom:4px;}
.ea-kpi .v{font-family:var(--serif); font-size:1.7rem; font-weight:600; color:var(--text); line-height:1.15;
  font-variant-numeric:lining-nums tabular-nums;}
.ea-kpi .v small{font-family:var(--sans); font-size:.85rem; font-weight:500; color:var(--muted); margin-left:4px;}
.ea-kpi .h{font-size:.76rem; color:var(--muted); margin-top:4px;}
.ea-kpi.accent{background:var(--green); border-color:var(--green);}
.ea-kpi.accent .l,.ea-kpi.accent .h,.ea-kpi.accent .v small{color:#D4EDE3;}
.ea-kpi.accent .v{color:#fff;}
/* Блок «формула» и заметки */
.ea-note{background:var(--card); border:1px solid var(--border); border-left:3px solid var(--green);
  border-radius:4px 12px 12px 4px; padding:10px 14px; color:var(--muted); font-size:.88rem; margin:8px 0; line-height:1.5;}
.ea-note.warn{border-left-color:var(--amber);}
.ea-note b{color:var(--text);}
.ea-step{display:inline-flex; align-items:center; gap:8px; padding:8px 12px; border-radius:10px; font-size:.88rem;
  font-weight:600; margin:4px 0 10px 0;}
.ea-step.todo{background:#F1F3F2; color:var(--muted);} .ea-step.mid{background:var(--amber-soft); color:var(--amber);}
.ea-step.ok{background:var(--green-soft); color:var(--green);}
.ea-file{display:flex; gap:12px; align-items:center; border:1px solid var(--border); border-radius:12px; padding:10px 12px; margin:6px 0 4px 0;}
.ea-file .ic{width:36px; height:36px; border-radius:10px; background:var(--green-soft); color:var(--green);
  display:flex; align-items:center; justify-content:center; font-weight:700;}
.ea-step::before{content:""; width:7px; height:7px; border-radius:50%; background:currentColor;}
.ea-file .n{font-weight:600; color:var(--text); font-size:.92rem; word-break:break-all;}
.ea-file .m{color:var(--muted); font-size:.8rem;}
.katex-display{margin:.5em 0 !important;}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def header(title, subtitle="", eyebrow="", status=None):
    """Шапка страницы. status = (текст, 'ok'|'wait'|'warn')."""
    pill = ""
    if status:
        text, kind = status
        cls = "" if kind == "ok" else kind
        pill = f"<span class='ea-pill {cls}'><span class='ea-dot'></span>{html.escape(text)}</span>"
    st.markdown(
        f"<div class='ea-head'><div>"
        + (f"<div class='ea-eyebrow'>{html.escape(eyebrow)}</div>" if eyebrow else "")
        + f"<div class='ea-title'>{html.escape(title)}</div>"
        + (f"<div class='ea-sub'>{subtitle}</div>" if subtitle else "")
        + f"</div>{pill}</div>", unsafe_allow_html=True)


def kpis(items, accent_first=False):
    """Карточки: items = [(подпись, значение, единица, подсказка), ...]. Значение None → «—»."""
    cells = []
    for i, it in enumerate(items):
        label, value, unit, hint = (list(it) + [None, None, None])[:4]
        v = "—" if value is None else html.escape(str(value))
        u = f"<small>{html.escape(unit)}</small>" if unit and value is not None else ""
        h = f"<div class='h'>{html.escape(hint)}</div>" if hint else ""
        cls = "ea-kpi accent" if accent_first and i == 0 else "ea-kpi"
        cells.append(f"<div class='{cls}'><div class='l'>{html.escape(label)}</div><div class='v'>{v}{u}</div>{h}</div>")
    st.markdown(f"<div class='ea-kpis'>{''.join(cells)}</div>", unsafe_allow_html=True)


def note(text, icon=None):
    """Заметка с цветной полосой слева. icon='⚠' → жёлтая полоса (предупреждение)."""
    cls = "ea-note warn" if icon == "⚠" else "ea-note"
    st.markdown(f"<div class='{cls}'>{text}</div>", unsafe_allow_html=True)


def step(text, kind="todo"):
    st.markdown(f"<div class='ea-step {kind}'>{html.escape(text)}</div>", unsafe_allow_html=True)


def file_card(name, meta):
    st.markdown(f"<div class='ea-file'><div class='ic'>▶</div><div><div class='n'>{html.escape(name)}</div>"
                f"<div class='m'>{html.escape(meta)}</div></div></div>", unsafe_allow_html=True)


def formulas(rows):
    """Формулы в рамке: rows = [(название, LaTeX), ...]."""
    with st.container(border=True):
        for name, tex in rows:
            if name:
                st.caption(name)
            st.latex(tex)
