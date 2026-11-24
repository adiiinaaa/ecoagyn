"""«Ластанудың таралуы» — концентрации в воздухе на разном расстоянии от дороги.

Берёт выбросы из раздела «Шығарындылар есебі», переводит их в мощность линейного
источника q и считает гауссову модель (формулы и источники — в core/dispersion.py
и MODULE_NOTES.md).
"""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.common import PALETTE, ROOT
from core.dispersion import (DISPLAY_UNIT, NORM_KEY, POLLUTANTS, distance_below, from_display,
                             line_concentration, model_warnings, pasquill_class, q_from_ecoagyn,
                             sigma_z_briggs_urban, sigma_z_total, to_display)
from views.state import cfg, current_run, params, show_fig
from views.ui import formulas, header, note

NAME_KZ = {"NOx": "NOx (NO₂ есебімен)", "CO": "CO", "PM2.5": "PM2.5"}
def _n(v):
    """Короткая запись числа (3 значащие цифры, десятичная запятая)."""
    return f"{v:.3g}".replace(".", ",")


NORM_KZ = {"max_single": "Максималды бір реттік ПДК", "daily_avg": "Орташа тәуліктік ПДК"}


def load_norms(c):
    """ПДК из norms.json (мг/м³) → г/м³. Пустые значения остаются None."""
    path = ROOT / c["dispersion"].get("norms_file", "norms.json")
    if not path.exists():
        return {}, None
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for key, v in data.get("pollutants", {}).items():
        out[key] = {k: (None if v.get(k) is None else v[k] / 1000.0) for k in ("max_single", "daily_avg")}
    return out, data


def _inputs(c):
    """Блок ввода параметров. Возвращает словарь параметров модели."""
    d = c["dispersion"]
    st.subheader("1. Метеорология және геометрия")
    u = st.number_input("Желдің жылдамдығы u, м/с (10 м биіктікте)", 0.1, 30.0, float(d["wind_speed_ms"]), 0.5)

    mode = st.radio("Атмосфераның тұрақтылық класы (Пасквилл)", ["Қолмен таңдау", "Пасквилл кестесі бойынша"],
                    horizontal=True)
    if mode == "Қолмен таңдау":
        stab = st.select_slider("Класс", list("ABCDEF"), value=d["stability"],
                                help="A — өте тұрақсыз (күшті күн), D — бейтарап, F — тұрақты (ашық түн)")
        stab_note = "қолмен таңдалды"
    else:
        a, b, e = st.columns(3)
        day = a.radio("Тәулік уақыты", ["Күндіз", "Түнде"], horizontal=True) == "Күндіз"
        overcast = e.checkbox("Тұтас бұлтты", help="Күндіз де, түнде де тұтас бұлт — D класы")
        if day:
            ins = b.selectbox("Күн радиациясы", ["strong", "moderate", "slight"], index=1,
                              format_func={"strong": "күшті", "moderate": "орташа", "slight": "әлсіз"}.get)
            stab, _, stab_note = pasquill_class(u, True, insolation=ins, overcast=overcast)
        else:
            cl = b.selectbox("Түнгі бұлттылық", ["cloudy", "clear"],
                             format_func={"cloudy": "бұлт ≥ 4/8", "clear": "бұлт ≤ 3/8"}.get)
            stab, _, stab_note = pasquill_class(u, False, night_cloud=cl, overcast=overcast)
        st.write(f"Класс: **{stab}** — {stab_note}. Кесте: Turner (1970), Table 1.")

    a, b, e = st.columns(3)
    h = a.number_input("Шығарынды биіктігі h, м", 0.0, 10.0, float(d["emission_height_m"]), 0.1)
    z = b.number_input("Бақылау нүктесі z, м (тыныс алу деңгейі)", 0.0, 10.0, float(d["receptor_height_m"]), 0.1)
    sz0 = e.number_input("Бастапқы шашырау σz0, м (жорамал)", 0.0, 10.0, float(d["sigma_z0_m"]), 0.1,
                         help="Көліктер тудыратын турбуленттілік. Әдепкі 1,5 м — жорамал, MODULE_NOTES.md қараңыз.")
    return {"u": u, "stability": stab, "stab_note": stab_note, "h": h, "z": z, "sz0": sz0}


def render():
    c = cfg()
    run = current_run()
    P = params()
    d = c["dispersion"]
    header("Ластанудың таралуы", "Шығарындыдан ауадағы концентрацияға: жолдан әр түрлі қашықтықта адам "
           "қандай ауамен тыныс алады.", "Экология")

    m = _inputs(c)

    st.subheader("2. Фон және норматив")
    norms, norms_doc = load_norms(c)
    a, b = st.columns([1, 2])
    norm_type = a.radio("Салыстыру", list(NORM_KZ), format_func=NORM_KZ.get,
                        index=list(NORM_KZ).index(d.get("norm_type", "max_single")))
    if norms_doc:
        b.caption(f"Норматив: {norms_doc.get('document', '—')}")
    cols = st.columns(len(POLLUTANTS))
    bg = {}
    for col, p in zip(cols, POLLUTANTS):
        v = col.number_input(f"Фон {NAME_KZ[p]}, {DISPLAY_UNIT[p]}", 0.0, 1e6, 0.0, 1.0 if DISPLAY_UNIT[p] == "мкг/м³" else 0.1)
        bg[p] = from_display(v, p)

    if m["u"] < 1.0:
        note(model_warnings(m["u"], 90)[0][1], "⚠")

    t1, t2 = st.tabs(["1-нұсқа: жол (қашықтық профилі)", "2-нұсқа: дау картасы (жол + қазандық)"])
    with t1:
        _version1(c, run, P, d, m, norms, norm_type, bg)
    with t2:
        from views.p10_map import render_map
        render_map(c, run, P, m, norms, norm_type, bg)


def _version1(c, run, P, d, m, norms, norm_type, bg):
    """Версия 1: дорога как линейный источник, профиль C(x)."""
    m = dict(m)
    m["theta"] = st.number_input("Жел мен жол арасындағы бұрыш θ, ° (90° — жолға көлденең)", 0.0, 90.0,
                                 float(d["wind_angle_deg"]), 5.0)
    for code, text in model_warnings(m["u"], m["theta"]):
        if code == "parallel":
            note(text, "⚠")

    # ---------- q ----------
    st.subheader("3. Көздің қуаты q")
    qd = q_from_ecoagyn(c, run, P)
    formulas([("Сызықтық көздің қуаты", r"q=\frac{E}{T\cdot L}\quad\left[\frac{\text{г}}{\text{м}\cdot\text{с}}\right]")])
    rows = []
    for p in POLLUTANTS:
        r = qd[p]
        rows.append({"Зат": NAME_KZ[p], "E, г (бейне ішінде)": round(r["E_g"], 3), "T, с": round(r["T_s"], 1),
                     "L, м": round(r["L_m"]), "q, г/(м·с)": f"{r['q']:.3e}"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("E «Шығарындылар есебі» бөлімінен алынады, ол L-ге пропорционал, сондықтан q учаске ұзындығына "
               "тәуелді емес: бұл жолдың 1 метрінің секундтағы шығарындысы.")

    # ---------- C(x) ----------
    st.subheader("4. Концентрация профилі C(x)")
    formulas([
        (None, r"C(x)=\frac{q}{\sqrt{2\pi}\,\sigma_z\,u\,\sin\theta}\left[e^{-\frac{(z-h)^2}{2\sigma_z^2}}"
               r"+e^{-\frac{(z+h)^2}{2\sigma_z^2}}\right]+C_{\text{фон}}"),
        ("σz — Briggs (1973), қала; машиналардың шашыратуы ескерілген", r"\sigma_z=\sqrt{\sigma_{z0}^2+\sigma_z^{B}(x/\sin\theta)^2}"),
    ])
    x = np.arange(d["x_min_m"], d["x_max_m"] + 0.25, 0.5)
    prof = {p: line_concentration(x, qd[p]["q"], m["u"], m["theta"], m["stability"], m["h"], m["z"], m["sz0"], bg[p])
            for p in POLLUTANTS}
    limits = {p: (norms.get(NORM_KEY[p]) or {}).get(norm_type) for p in POLLUTANTS}

    fig, axs = plt.subplots(1, len(POLLUTANTS), figsize=(13, 3.8))
    for ax, p, colr in zip(axs, POLLUTANTS, PALETTE):
        yv = to_display(prof[p], p)
        ax.plot(x, yv, color=colr, lw=2)
        ax.set_ylim(0, yv.max() * 1.15)
        if limits[p]:
            lim_v = to_display(limits[p], p)
            if lim_v <= yv.max() * 3:          # норматив рядом с кривой — рисуем линию
                ax.axhline(lim_v, color="#C2553F", ls="--", lw=1.2, label="ПДК")
                ax.set_ylim(0, max(yv.max(), lim_v) * 1.15)
                ax.legend(fontsize=8)
            else:                               # норматив намного выше — подпись, чтобы не сплющить кривую
                ax.text(0.98, 0.95, f"ПДК = {_n(lim_v)} {DISPLAY_UNIT[p]}\n(графиктен жоғары, "
                        f"{lim_v / yv.max():.0f}× артық)", transform=ax.transAxes, ha="right", va="top",
                        fontsize=8, color="#C2553F")
        ax.set_xscale("log")
        ax.set_xlabel("Жолдан қашықтық x, м")
        ax.set_ylabel(DISPLAY_UNIT[p])
        ax.set_title(NAME_KZ[p])
    fig.suptitle(f"u = {m['u']:g} м/с, θ = {m['theta']:g}°, класс {m['stability']}, z = {m['z']:g} м", fontsize=10)
    fig.tight_layout()
    show_fig(fig, run, "dispersion_profiles")

    # ---------- Таблица ----------
    st.subheader("5. Кесте")
    dist = d["table_distances_m"]
    tab = {"x, м": dist}
    for p in POLLUTANTS:
        v = to_display(line_concentration(np.array(dist, float), qd[p]["q"], m["u"], m["theta"], m["stability"],
                                          m["h"], m["z"], m["sz0"], bg[p]), p)
        tab[f"{NAME_KZ[p]}, {DISPLAY_UNIT[p]}"] = [float(f"{t:.3g}") for t in v]   # 3 значащие цифры
    tdf = pd.DataFrame(tab)
    st.dataframe(tdf, hide_index=True, width="stretch")
    tdf.to_csv(run["dir"] / "dispersion_table.csv", index=False, encoding="utf-8-sig")

    # ---------- Расстояние до норматива ----------
    st.subheader("6. ПДК-дан төмен түсетін қашықтық")
    rows = []
    for p in POLLUTANTS:
        val, status = distance_below(x, prof[p], limits[p])
        text = {"ok": f"{val:.0f} м", "already": f"жолдың жанында-ақ ({x[0]:.0f} м) ПДК-дан төмен",
                "beyond": f"{x[-1]:.0f} м-ге дейін ПДК-дан жоғары", "no_limit": "норматив енгізілмеген"}[status]
        lim = "—" if not limits[p] else _n(to_display(limits[p], p))
        rows.append({"Зат": NAME_KZ[p], f"{NORM_KZ[norm_type]}, бірлік": f"{lim} {DISPLAY_UNIT[p]}",
                     "Максимум (x = 5 м)": f"{_n(to_display(prof[p][0], p))} {DISPLAY_UNIT[p]}", "Қашықтық": text})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if norm_type == "daily_avg":
        note("Модель қысқа мерзімді (шамамен бір сағаттық) концентрацияны береді. Орташа тәуліктік ПДК-мен "
             "салыстыру — шамамен ғана, өйткені тәулік ішінде жел мен ағын өзгереді.", "⚠")
    note("NOx толығымен NO₂ деп есептеледі және NO₂ нормативімен салыстырылады — бұл қор есебімен баға "
         "(шын мәнінде NOx-тің бір бөлігі — NO).")

    # ---------- Пример расчёта вручную ----------
    with st.expander("Бір нүктенің қадамдық есебі (NOx, x = 100 м)"):
        s = np.sin(np.radians(m["theta"]))
        szb = float(sigma_z_briggs_urban(100 / s, m["stability"]))
        sz = float(sigma_z_total(100 / s, m["stability"], m["sz0"]))
        a1 = np.exp(-(m["z"] - m["h"]) ** 2 / (2 * sz ** 2))
        a2 = np.exp(-(m["z"] + m["h"]) ** 2 / (2 * sz ** 2))
        q = qd["NOx"]["q"]
        cval = q / (np.sqrt(2 * np.pi) * sz * m["u"] * s) * (a1 + a2)
        st.latex(rf"\sigma_z^{{B}}({100 / s:.1f})={szb:.3f}\ \text{{м}},\quad \sigma_z=\sqrt{{{m['sz0']:g}^2+{szb:.3f}^2}}={sz:.3f}\ \text{{м}}")
        st.latex(rf"e^{{-\frac{{({m['z']:g}-{m['h']:g})^2}}{{2\sigma_z^2}}}}+e^{{-\frac{{({m['z']:g}+{m['h']:g})^2}}{{2\sigma_z^2}}}}"
                 rf"={a1:.4f}+{a2:.4f}={a1 + a2:.4f}")
        st.latex(rf"C=\frac{{{q:.3e}}}{{2{{,}}5066\cdot{sz:.3f}\cdot{m['u']:g}\cdot{s:.3f}}}\cdot{a1 + a2:.4f}"
                 rf"={cval:.3e}\ \text{{г/м}}^3={cval * 1e6:.2f}\ \text{{мкг/м}}^3")

    st.subheader("Жорамалдар")
    for t in ["Жер беті тегіс, ғимараттар мен ағаштар ескерілмейді.",
              "Жел тұрақты (стационар), бағыты мен жылдамдығы есептеу кезінде өзгермейді.",
              "Химиялық айналулар жоқ (NO → NO₂, бөлшектердің түзілуі ескерілмейді).",
              "Жол — шексіз ұзын түзу сызық; қиылыс пен бұрылыстар ескерілмейді.",
              "Нәтиже — есептік баға, өлшеу емес. Толығырақ: MODULE_NOTES.md."]:
        st.markdown(f"- {t}")
