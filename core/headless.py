"""Фоновая отрисовка всех разделов без браузера — чтобы в отчёт попали все графики.

Streamlit без сервера работает в «bare mode»: виджеты возвращают значения
по умолчанию, а show_fig сохраняет PNG. Параметры расчёта передаются через
params.json (то, что пользователь изменил на сайте).
Запуск: python -m core.headless <имя_видео> <params.json>
"""
import json
import logging
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)


def main(name, params_path):
    import streamlit as st
    from views import state
    from views import (p1_video, p3_accuracy, p4_emissions, p5_uncertainty,  # noqa: F401
                       p6_flow, p7_scenarios, p8_ecology, p9_method)

    P = json.loads(Path(params_path).read_text(encoding="utf-8"))
    get_params = lambda: P                                                      # noqa: E731  параметры с сайта
    get_run = lambda required=True: state.load_run(state.cfg(), name)           # noqa: E731
    st.session_state["run_name"] = name
    for mod in (p1_video, p3_accuracy, p4_emissions, p5_uncertainty, p6_flow, p7_scenarios, p8_ecology):
        if hasattr(mod, "params"):
            mod.params = get_params
        if hasattr(mod, "current_run"):
            mod.current_run = get_run
        try:
            mod.render() if mod is not p1_video else mod._show_results()
        except Exception as e:                  # один раздел не должен ломать отчёт
            print(f"[{mod.__name__}] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
