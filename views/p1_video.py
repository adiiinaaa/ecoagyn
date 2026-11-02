"""«Бейне және санау» — видео и подсчёт.

Экран построен вокруг задачи: увидеть дорогу → отметить линию → запустить анализ.
Слева крупный кадр (2/3 ширины), справа настройки (1/3), ниже — карточки результата.
"""
from pathlib import Path

import cv2
import streamlit as st
from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from core.analysis import annotated_video, chart_intervals, interval_counts, load_run, summary_table
from core.common import ROOT, font, list_videos, processed_videos
from core.counting import read_frame, run_counting, video_info
from views.state import cfg, fmt, show_fig
from views.ui import file_card, header, kpis, note, step

YELLOW = (0, 215, 255)   # BGR


def _mmss(s):
    s = int(round(s))
    return f"{s // 60:02d}:{s % 60:02d}"


def _preview(frame, pts):
    """Кадр с точками A, B, линией и стрелкой «1-бағыт»."""
    img = frame.copy()
    th = max(2, img.shape[1] // 450)
    if len(pts) == 2:
        a, b = [tuple(map(int, p)) for p in pts]
        cv2.line(img, a, b, YELLOW, th + 2, cv2.LINE_AA)
        mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
        nx, ny = -(b[1] - a[1]), (b[0] - a[0])
        n = max(1.0, (nx ** 2 + ny ** 2) ** 0.5)
        L = img.shape[1] * 0.05
        cv2.arrowedLine(img, (mx, my), (int(mx + nx / n * L), int(my + ny / n * L)), YELLOW, th + 1,
                        cv2.LINE_AA, tipLength=0.35)
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d =ImageDraw.Draw(pil)
    r = th * 7
    f = font(int(r * 1.3))
    for p, lab in zip(pts, "AB"):
        x, y = map(int, p)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(22, 125, 97), outline=(255, 255, 255), width=th)
        d.text((x, y), lab, font=f, fill=(255, 255, 255), anchor="mm")
    if len(pts) == 2:
        (ax, ay), (bx, by) = pts
        mx, my = (ax + bx) / 2, (ay + by) / 2
        nx, ny = -(by - ay), (bx - ax)
        n = max(1.0, (nx ** 2 + ny ** 2) ** 0.5)
        L = img.shape[1] * 0.05
        d.text((mx + nx / n * L * 1.25, my + ny / n * L * 1.25), "1", font=f, fill=(255, 215, 0), anchor="mm",
               stroke_width=th, stroke_fill=(0, 0, 0))
    return pil


def _set_pts(key, pts):
    """Записывает точки и синхронизирует поля координат."""
    st.session_state[key] = pts
    if len(pts) == 2:
        for (n, v) in zip(("x1", "y1", "x2", "y2"), [*pts[0], *pts[1]]):
            st.session_state[f"{n}::{key}"] = int(v)


def _from_inputs(key):
    s = st.session_state
    st.session_state[key] = [[s[f"x1::{key}"], s[f"y1::{key}"]], [s[f"x2::{key}"], s[f"y2::{key}"]]]


def cloud_mode():
    """Онлайн-версия (Streamlit Cloud): нейросети нет — только просмотр готовых результатов."""
    import importlib.util
    return importlib.util.find_spec("ultralytics") is None


def render():
    c = cfg()
    if cloud_mode():
        _render_cloud()
        return
    vids = list_videos(c)

    # ---------- Выбор видео (в правой колонке, но нужен заранее) ----------
    src = st.session_state.get("src_mode", "Кітапхана")
    video_path = st.session_state.get("video_path")
    if src == "Кітапхана" and vids and (video_path is None or Path(video_path) not in vids):
        video_path = vids[0]

    done = video_path is not None and Path(video_path).stem in processed_videos(c)
    status = (("Талдау аяқталды", "ok") if done else ("Бейне таңдалды", "warn")) if video_path else ("Бейне жоқ", "wait")
    header("Бейне және санау", "Бейнені таңдаңыз, санау сызығын белгілеңіз және талдауды іске қосыңыз.",
           "Талдау", status)

    left, right = st.columns([2, 1], gap="large")

    # ---------- Правая колонка: настройки ----------
    with right:
        with st.container(border=True):
            st.markdown("**Файл**")
            src = st.segmented_control("Көзі", ["Кітапхана", "Файл жүктеу"], default=src,
                                       key="src_mode", label_visibility="collapsed") or "Кітапхана"
            if src == "Кітапхана":
                if vids:
                    video_path = st.selectbox("Бейне", vids, index=vids.index(Path(video_path)) if video_path in vids else 0,
                                              format_func=lambda p: p.name, label_visibility="collapsed")
                else:
                    st.caption("videos/ папкасында бейне жоқ.")
            else:
                up = st.file_uploader("mp4 / mov", type=["mp4", "mov"], label_visibility="collapsed")
                if up is not None:
                    dst = ROOT / "videos" / up.name
                    dst.parent.mkdir(exist_ok=True)
                    if not dst.exists() or dst.stat().st_size != up.size:
                        with open(dst, "wb") as f:
                            f.write(up.getbuffer())
                    video_path = dst
            st.session_state.video_path = video_path

    if video_path is None:
        with left:
            with st.container(border=True):
                st.markdown("<div style='height:320px;display:flex;align-items:center;justify-content:center;"
                            "color:#66756F'>Бейне таңдаңыз немесе жүктеңіз</div>", unsafe_allow_html=True)
        return

    info = video_info(video_path)
    key = f"pts::{Path(video_path).name}"
    if key not in st.session_state:
        h, w = info["height"], info["width"]
        _set_pts(key, [[int(w * 0.25), int(h * 0.68)], [int(w * 0.75), int(h * 0.68)]])
    pts = st.session_state[key]

    # ---------- Левая колонка: крупный кадр ----------
    with left:
        with st.container(border=True):
            t = st.session_state.get("t_frame", 0.0)
            frame = read_frame(video_path, t)
            click = streamlit_image_coordinates(_preview(frame, pts), width="stretch", key=f"img::{key}",
                                                image_format="JPEG", jpeg_quality=85, cursor="crosshair")
            if click and click != st.session_state.get(f"last::{key}"):
                st.session_state[f"last::{key}"] = click
                s = frame.shape[1] / click["width"]                  # экранные пиксели → пиксели кадра
                p = [round(click["x"] * s), round(click["y"] * s)]
                _set_pts(key, pts + [p] if len(pts) == 1 else [p])   # третий клик начинает заново
                st.rerun()
            st.slider(f"Кадр: {_mmss(t)} / {_mmss(info['duration_s'])}", 0.0,
                      max(1.0, info["duration_s"] - 1), key="t_frame", step=1.0, format="%.0f с")
        note("<b>Құпиялылық.</b> Нөмірлер танылмайды және сақталмайды: барлық сақталатын кадрларда, бейнеде "
             "және кескіндерде нөмір аймағы мен адамдардың басы бұлдырлатылады.", "🛡")

    # ---------- Правая колонка: линия и запуск ----------
    with right:
        with st.container(border=True):
            file_card(Path(video_path).name, f"{info['width']}×{info['height']} · {info['fps']:.0f} FPS · "
                                             f"{_mmss(info['duration_s'])}")
            st.markdown("**Санау сызығы**")
            if len(pts) == 0:
                step("1. Кадрдан бірінші нүктені (A) таңдаңыз", "todo")
            elif len(pts) == 1:
                step("2. Енді екінші нүктені (B) таңдаңыз", "mid")
            else:
                step("Сызық дайын — талдауды бастауға болады", "ok")
            b1, b2 = st.columns(2)
            if b1.button("Тазалау", icon=":material/restart_alt:", width="stretch"):
                _set_pts(key, [])
                st.rerun()
            if b2.button("Бағыт", icon=":material/swap_horiz:", width="stretch", disabled=len(pts) != 2,
                         help="1-бағыт пен 2-бағытты ауыстыру"):
                _set_pts(key, pts[::-1])
                st.rerun()
            with st.expander("Нүктелердің координаттары"):
                cc = st.columns(2)
                for i, n in enumerate(("x1", "y1", "x2", "y2")):
                    lim = info["width"] if n.startswith("x") else info["height"]
                    st.session_state.setdefault(f"{n}::{key}", 0)
                    cc[i % 2].number_input(n, 0, lim, key=f"{n}::{key}", on_change=_from_inputs, args=(key,))
            with st.expander("Қосымша баптаулар"):
                cc = st.columns(2)
                start = cc[0].number_input("Басы, с", 0.0, info["duration_s"], 0.0, 1.0)
                end = cc[1].number_input("Соңы, с", 0.0, info["duration_s"], info["duration_s"], 1.0)
                d1 = cc[0].text_input("1-бағыт атауы", "1-бағыт")
                d2 = cc[1].text_input("2-бағыт атауы", "2-бағыт")
                det = c["detection"]
                models = ["yolo11n.pt", "yolo11s.pt", "yolo11m.pt"]
                det["model"] = st.selectbox("YOLO моделі", models, index=models.index(det["model"]))
                det["imgsz"] = st.select_slider("Кіріс өлшемі (imgsz)", [480, 640, 800, 960, 1280], det["imgsz"])
                cc = st.columns(2)
                det["frame_step"] = cc[0].number_input("Әр N-ші кадр", 1, 6, det["frame_step"])
                det["confidence"] = cc[1].number_input("Сенімділік шегі", 0.1, 0.9, det["confidence"], 0.05)
                st.caption("Ноутбукты зарядтағышқа қосыңыз — батареяда видеокарта баяулайды.")
            go = st.button("Талдауды бастау", icon=":material/arrow_forward:", type="primary", width="stretch",
                           disabled=len(pts) != 2)
            if len(pts) != 2:
                st.caption("Бастау үшін екі нүкте керек.")
            if go:
                st.button("Тоқтату", icon=":material/stop:", width="stretch")   # нажатие прерывает расчёт
                bar = st.progress(0.0, "Дайындалуда…")
                s = run_counting(video_path, pts, c, start, end, [d1, d2],
                                 progress=lambda f, t_: bar.progress(min(1.0, f), t_))
                st.session_state.run_name = Path(video_path).stem
                st.session_state.pop("report_ready", None)
                bar.progress(1.0, f"Дайын: {s['total']} көлік")
                st.rerun()

    # ---------- Карточки результата ----------
    run = load_run(c, Path(video_path).stem) if done else None
    if run:
        s = run["summary"]
        per_h = s["total"] * 3600 / s["duration_s"]
        kpis([("Көлік саны", s["total"], "көлік", f"{_mmss(s['from_s'])}–{_mmss(s['to_s'])} кесіндісінде"),
              ("Қарқындылық", fmt(per_h, 0), "көлік/сағ", "сағатқа қайта есептелген"),
              ("Өңдеу уақыты", fmt(s["processing_s"] / 60, 1), "мин", f"imgsz {s['imgsz']}, әр {s['frame_step']}-кадр"),
              ("Мәртебе", "Аяқталды", None, "нәтижелер results/ папкасында")], accent_first=True)
    else:
        kpis([("Көлік саны", None), ("Қарқындылық", None), ("Өңдеу уақыты", None), ("Мәртебе", "Іске қосылмаған")])
        return
    _results(run)


def _render_cloud():
    """Онлайн-версия: показываем результаты выбранного в меню видео."""
    from views.state import current_run
    header("Бейне және санау", "Онлайн-нұсқа: дайын нәтижелерді көру. Жаңа бейнені өңдеу (нейрондық желі) — "
           "компьютердегі нұсқада.", "Талдау", ("Онлайн-нұсқа", "ok"))
    run = current_run()
    s = run["summary"]
    left, right = st.columns([2, 1], gap="large")
    with left:
        p = run["dir"] / "stand_frame.png"
        if p.exists():
            st.image(str(p))
    with right:
        with st.container(border=True):
            file_card(s["video_name"], f"{s['width']}×{s['height']} · {s['fps']:.0f} FPS · {_mmss(s['duration_s'])}")
            st.markdown("**Санау сызығы**")
            step(f"A({s['line'][0][0]}; {s['line'][0][1]}) → B({s['line'][1][0]}; {s['line'][1][1]})", "ok")
            st.caption(f"YOLO: {s['model']}, imgsz {s['imgsz']}, әр {s['frame_step']}-кадр · ByteTrack")
    note("<b>Құпиялылық.</b> Нөмірлер танылмайды және сақталмайды: барлық кадрларда нөмір аймағы мен "
         "адамдардың басы бұлдырлатылған.")
    per_h = s["total"] * 3600 / s["duration_s"]
    kpis([("Көлік саны", s["total"], "көлік", f"{_mmss(s['from_s'])}–{_mmss(s['to_s'])} кесіндісінде"),
          ("Қарқындылық", fmt(per_h, 0), "көлік/сағ", "сағатқа қайта есептелген"),
          ("Өңдеу уақыты", fmt(s["processing_s"] / 60, 1), "мин", f"imgsz {s['imgsz']}, әр {s['frame_step']}-кадр"),
          ("Мәртебе", "Аяқталды", None, "онлайн-нұсқа")], accent_first=True)
    _results(run)


def _results(run):
    c = cfg()
    s = run["summary"]
    if s["duration_s"] < 300:
        note("Бейне 5 минуттан қысқа: сағатқа шаққандағы мән жуық. Зерттеу үшін 15–20 минут түсіріңіз.", "⚠")
    t1, t2, t3, t4 = st.tabs(["Кесте", "Уақыт бойынша", "Рамкалары бар бейне", "Стенд кадры"])
    with t1:
        tab = summary_table(c, run)
        st.dataframe(tab.drop(columns=["class"]), hide_index=True, width="stretch")
        st.latex(r"N_{\text{сағ}} = N \cdot \frac{3600}{T} = " + f"{s['total']}" + r"\cdot\frac{3600}{"
                 + f"{s['duration_s']:.1f}" + r"} \approx " + f"{s['total'] * 3600 / s['duration_s']:.0f}"
                 + r"\ \text{көлік/сағ}")
    with t2:
        for width, name, title in [(60, "per_minute", "Әр минуттағы көлік саны"),
                                   (30, "per_30s", "Әр 30 секундтағы көлік саны")]:
            df = interval_counts(run["events"], s["from_s"], s["to_s"], width)
            show_fig(chart_intervals(c, df, width, title), run, name)
    with t3:
        v = annotated_video(run)
        if v.exists():
            st.video(str(v))
    with t4:
        p = run["dir"] / "stand_frame.png"
        if p.exists():
            st.image(str(p))
            st.download_button("PNG жүктеу", p.read_bytes(), "stand_frame.png", "image/png", icon=":material/download:")


# Для фонового отчёта (core/headless.py)
def _show_results():
    from views.state import current_run
    run = current_run(required=False)
    if run is None:
        return
    s = run["summary"]
    for width, name, title in [(60, "per_minute", "Әр минуттағы көлік саны"),
                               (30, "per_30s", "Әр 30 секундтағы көлік саны")]:
        df = interval_counts(run["events"], s["from_s"], s["to_s"], width)
        show_fig(chart_intervals(cfg(), df, width, title), run, name)
