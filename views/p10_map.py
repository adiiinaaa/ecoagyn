"""Вкладка «2-нұсқа: дау картасы» страницы «Ластанудың таралуы».

Дорога + котельная + фон на сетке вокруг перекрёстка, индексы M (по худшему веществу)
и S (по сумме) и индекс спорности. Формулы — в core/dispersion_map.py и MODULE_NOTES.md.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from core.common import PALETTE
from core.dispersion import model_warnings, q_from_ecoagyn
from core.dispersion_map import (MAP_NORM_KEY, MAP_POLLUTANTS, compute_map, make_grid, road_so2_q, road_vectors,
                                 summary_tables, wind_vector)
from views.state import show_fig
from views.ui import formulas, note

NAME = {"NOx": "NOx (NO₂)", "SO2": "SO₂", "PM2.5": "PM2.5", "CO": "CO"}
# Порядок цветов для «худшего вещества»: серый — нет загрязнения
WORST_COLORS = {"NOx": PALETTE[0], "SO2": PALETTE[1], "PM2.5": PALETTE[2], "CO": PALETTE[3]}


def _draw_sources(ax, half, road_az, wind_from, bx, by):
    """Дорога (линия), котельная (звёздочка) и стрелка ветра на карте."""
    r, _ = road_vectors(road_az)
    ax.plot([-r[0] * half * 1.5, r[0] * half * 1.5], [-r[1] * half * 1.5, r[1] * half * 1.5],
            color="#182522", lw=2.2, label="Жол")
    ax.plot([bx], [by], marker="*", ms=16, color="#C2553F", mec="white", label="Қазандық")
    w = wind_vector(wind_from)
    ax.annotate("", xy=(-half * 0.72 + w[0] * 120, half * 0.82 + w[1] * 120), xytext=(-half * 0.72, half * 0.82),
                arrowprops=dict(arrowstyle="-|>", color="#182522", lw=2))
    ax.text(-half * 0.72, half * 0.92, "жел", ha="center", fontsize=9)
    ax.set_xlim(-half, half)
    ax.set_ylim(-half, half)
    ax.set_xlabel("Шығыс бағыты, м")
    ax.set_ylabel("Солтүстік бағыты, м")
    ax.set_aspect("equal")
    ax.grid(False)


def render_map(c, run, P, m, norms, norm_type, bg):
    dm = c["dispersion_map"]
    b = dm["boiler"]
    note("<b>Дау картасы.</b> Әр клеткада xᵢ = Cᵢ/ПДКᵢ, M = max xᵢ (ең нашар зат) және S = Σ xᵢ (қосынды) "
         "есептеледі. Екі клетканы M бір ретпен, ал S қарама-қарсы ретпен салыстырса — бұл «дау»: "
         "қай жер лас екені формулаға байланысты.")
    formulas([(None, r"x_i=\frac{C_i}{\text{ПДК}_i},\quad M=\max_i x_i,\quad S=\sum_i x_i,\quad "
                     r"D_k=\frac{1}{n-1}\#\{\,j:\ (M_k-M_j)(S_k-S_j)<0\,\}")])

    st.markdown("**Жел және жол**")
    a, b2, e = st.columns(3)
    wind_from = a.number_input("Жел қайдан соғады, ° (270° — батыстан)", 0.0, 359.0, float(dm["wind_from_deg"]), 5.0)
    road_az = b2.number_input("Жолдың бағыты (азимут), ° (0° — солтүстік–оңтүстік)", 0.0, 179.0,
                              float(dm["road_azimuth_deg"]), 5.0)
    half = e.number_input("Карта: жартылай өлшемі, м", 100.0, 2000.0, float(dm["grid_half_size_m"]), 50.0)
    step = float(dm["grid_step_m"])

    st.markdown("**Қазандық — нүктелік көз** (әдепкі мәндер — **шартты**, нақты қазандық деректері емес)")
    a, b2, e = st.columns(3)
    bx = a.number_input("Қазандық x, м (шығысқа)", -2000.0, 2000.0, float(b["x_m"]), 10.0)
    by = b2.number_input("Қазандық y, м (солтүстікке)", -2000.0, 2000.0, float(b["y_m"]), 10.0)
    H = e.number_input("Мұржа биіктігі H, м", 1.0, 300.0, float(b["stack_height_m"]), 1.0)
    cols = st.columns(4)
    Q = {p: cols[i].number_input(f"Q {NAME[p]}, г/с (шартты)", 0.0, 1000.0, float(b["q_g_s"][p]), 0.1)
         for i, p in enumerate(MAP_POLLUTANTS)}

    st.markdown("**Жолдан SO₂** — EMEP/EEA: E = 2·k_S·FC (Table 3-14, «Fuel 2009 and later»)")
    sp = dm["road_so2"]["sulphur_ppm"]
    a, b2, e = st.columns(3)
    ks = dict(sp)
    ks["petrol"] = a.number_input("Бензиндегі күкірт, ppm", 0.0, 2000.0, float(sp["petrol"]), 1.0)
    ks["diesel"] = b2.number_input("Дизельдегі күкірт, ppm", 0.0, 2000.0, float(sp["diesel"]), 1.0)
    bg_so2 = e.number_input("Фон SO₂, мкг/м³", 0.0, 1e6, 0.0, 1.0) / 1e6

    # q дороги: NOx, CO, PM2.5 — из EcoAgyn (как в версии 1), SO2 — по сере в топливе
    qd = q_from_ecoagyn(c, run, P)
    q = {p: qd[p]["q"] for p in ("NOx", "CO", "PM2.5")}
    q["SO2"] = road_so2_q(c, run, P, ks)
    background = dict(bg)
    background["SO2"] = bg_so2
    limits = {p: (norms.get(MAP_NORM_KEY[p]) or {}).get(norm_type) for p in MAP_POLLUTANTS}
    missing = [NAME[p] for p in MAP_POLLUTANTS if not limits[p]]
    if missing:
        note("ПДК енгізілмеген, M және S-ке кірмейді: " + ", ".join(missing), "⚠")

    X, Y = make_grid(half, step)
    res = compute_map(X, Y, q, Q, background, limits, m["u"], wind_from, road_az, m["stability"], m["h"], m["z"],
                      m["sz0"], bx, by, H, c["dispersion_map"]["near_road_min_m"])
    st.caption(f"Жел мен жол арасындағы бұрыш θ = {res['theta']:.0f}° · класс {m['stability']} · u = {m['u']:g} м/с · "
               f"тор {X.shape[0]}×{X.shape[1]} = {X.size} клетка, қадам {step:g} м")
    for code, text in model_warnings(m["u"], res["theta"]):
        if code == "parallel":
            note(text, "⚠")

    # ---------- Две карты ----------
    ext = [X.min() - step / 2, X.max() + step / 2, Y.min() - step / 2, Y.max() + step / 2]
    a, b2 = st.columns(2)
    with a:
        fig, ax = plt.subplots(figsize=(6.2, 5.6))
        im = ax.imshow(res["dispute"], origin="lower", extent=ext, cmap="magma_r", vmin=0)
        _draw_sources(ax, half, road_az, wind_from, bx, by)
        fig.colorbar(im, ax=ax, shrink=0.8, label="Даулылық индексі (клеткалар үлесі)")
        ax.set_title("Даулылық индексі")
        ax.legend(loc="lower right", fontsize=8, frameon=True, facecolor="white", framealpha=0.9)
        fig.tight_layout()
        show_fig(fig, run, "dispute_map")
    with b2:
        names = res["names"]
        colors = ["#D9DED9"] + [WORST_COLORS[p] for p in names]
        fig, ax = plt.subplots(figsize=(6.2, 5.6))
        ax.imshow(res["worst"] + 1, origin="lower", extent=ext, cmap=ListedColormap(colors),
                  vmin=-0.5, vmax=len(names) + 0.5, interpolation="nearest")
        _draw_sources(ax, half, road_az, wind_from, bx, by)
        handles = [Patch(facecolor=col, edgecolor="#B9C4BF") for col in colors]
        ax.legend(handles, ["ластанбаған"] + [NAME[p] for p in names], loc="lower right", fontsize=8,
                  title="M бойынша ең нашар", title_fontsize=8, frameon=True, facecolor="white", framealpha=0.9)
        ax.set_title("Ең нашар зат (M бойынша)")
        fig.tight_layout()
        show_fig(fig, run, "worst_pollutant_map")

    # ---------- Итоги ----------
    per_pol, overall = summary_tables(res)
    a, b2 = st.columns(2)
    a.dataframe(pd.DataFrame(per_pol).round(4), hide_index=True, width="stretch")
    b2.dataframe(pd.DataFrame(overall).round(4), hide_index=True, width="stretch")
    # Итоговая таблица в одном простом формате: бөлім / көрсеткіш / мән
    rows = []
    for r in per_pol:
        rows.append({"Бөлім": r["Зат"], "Көрсеткіш": "max xᵢ = C/ПДК", "Мән": round(r["max xᵢ = C/ПДК"], 4)})
        rows.append({"Бөлім": r["Зат"], "Көрсеткіш": "ең нашар клеткалар үлесі, %",
                     "Мән": round(r["Ең нашар клеткалар үлесі, %"], 2)})
    rows += [{"Бөлім": "жалпы", "Көрсеткіш": r["Көрсеткіш"], "Мән": round(r["Мән"], 4)} for r in overall]
    pd.DataFrame(rows).to_csv(run["dir"] / "dispute_summary.csv", index=False, encoding="utf-8-sig")

    with st.expander("M және S карталары"):
        a, b2 = st.columns(2)
        for col, key, title in [(a, "M", "M = max xᵢ"), (b2, "S", "S = Σ xᵢ")]:
            with col:
                fig, ax = plt.subplots(figsize=(5.6, 5.0))
                im = ax.imshow(res[key], origin="lower", extent=ext, cmap="YlOrRd", vmin=0)
                _draw_sources(ax, half, road_az, wind_from, bx, by)
                fig.colorbar(im, ax=ax, shrink=0.8)
                ax.set_title(title)
                fig.tight_layout()
                st.pyplot(fig, width="stretch")
                plt.close(fig)

    note("Бір ғана көз болса (мысалы, Q = 0), барлық клеткада заттардың арақатынасы бірдей, M мен S бір "
         "ретпен өседі — дау болмайды. Дау екі көздің «профилі» әртүрлі болғанда пайда болады: жолда NOx басым, "
         "қазандықта — SO₂.")
    st.markdown("**Жорамалдар (2-нұсқа):** түтін көтерілуі ескерілмейді (тиімді биіктік = H, қазандыққа жақын "
                "концентрация жоғарырақ шығады — қор есебімен); жел барлық биіктікте бірдей; жол — орталықтан "
                "өтетін шексіз түзу; жолдың желге қарсы жағында оның үлесі 0. Толығырақ: MODULE_NOTES.md.")
