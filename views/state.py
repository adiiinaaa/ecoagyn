"""Общее состояние сайта: настройки, выбранное видео, параметры расчёта."""
import copy

import matplotlib.pyplot as plt
import streamlit as st

from core.analysis import load_run
from core.common import load_config, processed_videos, save_fig
from core.emissions import default_params


def cfg():
    if "cfg" not in st.session_state:
        st.session_state.cfg = load_config()
    return st.session_state.cfg


def params():
    """Параметры расчёта (меняются в разделе 4 и используются в 5, 7, 8)."""
    if "params" not in st.session_state:
        st.session_state.params = default_params(cfg())
    return st.session_state.params


def reset_params():
    st.session_state.params = default_params(cfg())


def run_names():
    return processed_videos(cfg())


def current_run(required=True):
    """Выбранное в боковом меню видео. Если нет — подсказка и остановка страницы."""
    name = st.session_state.get("run_name")
    if not name or name not in run_names():
        if required:
            st.info("Алдымен «Бейне және санау» бөлімінде бейнені өңдеңіз немесе бүйір мәзірден "
                    "өңделген бейнені таңдаңыз.")
            st.stop()
        return None
    # Кэш в сессии: перечитываем, только если файлы изменились
    key = f"run::{name}"
    run = load_run(cfg(), name)
    st.session_state[key] = run
    return run


def show_fig(fig, run, name):
    """Показывает график и сохраняет PNG (300 dpi) в results/<видео>/png/."""
    st.pyplot(fig, width="stretch")
    if run is not None:
        save_fig(fig, run["dir"] / "png" / f"{name}.png")
    plt.close(fig)


def fmt(x, nd=2):
    """Число в казахском стиле: пробел между тысячами, запятая в дробной части."""
    if x is None:
        return "—"
    try:
        s = f"{x:,.{nd}f}"
    except (TypeError, ValueError):
        return str(x)
    return s.replace(",", " ").replace(".", ",")


def deep(x):
    return copy.deepcopy(x)
