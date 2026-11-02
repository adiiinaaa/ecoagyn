"""EcoAgyn — көлік ағыны, математикалық модельдер және экология.

Запуск:  streamlit run app.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="EcoAgyn", page_icon=str(ROOT / "assets" / "logo.svg"), layout="wide")

from core.report import build_report  # noqa: E402
from views import (p1_video, p3_accuracy, p4_emissions, p5_uncertainty, p6_flow,  # noqa: E402
                   p7_scenarios, p8_ecology, p9_method)
from views.state import run_names  # noqa: E402
from views.ui import inject_css  # noqa: E402

inject_css()
st.logo(str(ROOT / "assets" / "logo.svg"), size="large")

# Меню сгруппировано по смыслу: сначала данные, затем математика, затем экология
PAGES = {
    "Талдау": [
        st.Page(p1_video.render, title="Бейне және санау", icon=":material/videocam:", url_path="video", default=True),
        st.Page(p3_accuracy.render, title="Дәлдікті тексеру", icon=":material/fact_check:", url_path="accuracy"),
    ],
    "Математика": [
        st.Page(p6_flow.render, title="Ағын статистикасы", icon=":material/bar_chart:", url_path="flow"),
        st.Page(p4_emissions.render, title="Шығарындылар есебі", icon=":material/functions:", url_path="emissions"),
        st.Page(p5_uncertainty.render, title="Белгісіздік", icon=":material/scatter_plot:", url_path="uncertainty"),
        st.Page(p7_scenarios.render, title="Сценарийлер", icon=":material/directions_bus:", url_path="scenarios"),
    ],
    "Экология": [
        st.Page(p8_ecology.render, title="Экологиялық қорытынды", icon=":material/eco:", url_path="ecology"),
    ],
    "Әдістеме": [
        st.Page(p9_method.render, title="Қалай есептелді?", icon=":material/menu_book:", url_path="method"),
    ],
}
nav = st.navigation(PAGES)

# Блок «Ағымдағы жоба» внизу меню: выбор обработанного видео и отчёт
with st.sidebar:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.caption("АҒЫМДАҒЫ ЖОБА")
    names = run_names()
    if names:
        cur = st.session_state.get("run_name")
        idx = names.index(cur) if cur in names else 0
        st.session_state.run_name = st.selectbox("Өңделген бейне", names, index=idx, label_visibility="collapsed")
        if st.button("Есепті дайындау", icon=":material/description:", width="stretch"):
            with st.spinner("Есеп жасалуда…"):
                html_path, zip_path = build_report(st.session_state.run_name, st.session_state)
            st.session_state.report_ready = (str(html_path), str(zip_path))
        if st.session_state.get("report_ready"):
            h, z = map(Path, st.session_state.report_ready)
            if h.exists():
                st.download_button("HTML есеп", h.read_bytes(), h.name, "text/html", icon=":material/download:",
                                   width="stretch", type="primary")
            if z.exists():
                st.download_button("Стендке PNG (zip)", z.read_bytes(), z.name, "application/zip",
                                   icon=":material/image:", width="stretch")
    else:
        st.caption("Әлі өңделген бейне жоқ.")

    # Адрес для телефона в той же Wi‑Fi сети (он может меняться после переподключения)
    import socket
    try:
        if p1_video.cloud_mode():                # в онлайн-версии адрес Wi‑Fi не нужен
            raise OSError
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.connect(("8.8.8.8", 80))              # пакет не отправляется — так узнаём свой IP в локальной сети
        _ip = _s.getsockname()[0]
        _s.close()
        st.caption(f"ТЕЛЕФОННАН АШУ (сол Wi‑Fi желісінде)  \n**http://{_ip}:8501**")
    except OSError:
        pass

nav.run()
