"""Раздел 5. «Белгісіздік» — неопределённость."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.common import PALETTE
from core.uncertainty import (LEVEL_KZ, corrected_counts, count_error, mc_stats, monte_carlo, scenarios,
                              tornado, variance_shares)
from views.state import cfg, current_run, fmt, params, show_fig
from views.ui import formulas, header, kpis, note

UNIT = {"CO2": "кг/сағ"}


def tornado_fig(rows, title, unit):
    base = rows[0][3]
    fig, ax = plt.subplots(figsize=(10, 0.6 * len(rows) + 1.5))
    for i, (name, lo, hi, _) in enumerate(rows):
        ax.barh(i, hi - base, left=base, color=PALETTE[1])
        ax.barh(i, lo - base, left=base, color=PALETTE[0])
        ax.text(hi, i, f"  {hi:.3g}", va="center", fontsize=9)
        ax.text(lo, i, f"{lo:.3g}  ", va="center", ha="right", fontsize=9)
    ax.axvline(base, color="black", lw=1)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xlabel(f"{title}, {unit}  (тік сызық — base = {base:.3g})")
    ax.set_title(f"Торнадо-диаграмма: {title}")
    ax.grid(axis="y", alpha=0)
    lo_, hi_ = min(r[1] for r in rows), max(r[2] for r in rows)
    pad = (hi_ - lo_) * 0.25 + 1e-9
    ax.set_xlim(lo_ - pad, hi_ + pad)
    fig.tight_layout()
    return fig


def render():
    c = cfg()
    run = current_run()
    P = params()
    pols = c["pollutants_main"]
    eps, eps_src = count_error(run, c)
    Nc = corrected_counts(run)
    header("Белгісіздік", "Нәтиже қаншалықты сенімді? Әр параметрдің ауқымын (low–high) ескеріп, CO2 және "
           "ластаушы заттардың ықтимал аралығын табамыз.", "Математика")
    mc = monte_carlo(c, run, P, eps, pols)
    kpis([("CO2 медианасы", fmt(np.median(mc["CO2"]), 1), "кг/сағ"),
          ("90% аралық (P5–P95)", f"{np.percentile(mc['CO2'], 5):.0f}–{np.percentile(mc['CO2'], 95):.0f}", "кг/сағ"),
          ("Санау қателігі ε", fmt(eps * 100, 1), "%", eps_src),
          ("Қате матрицасы", "бар" if Nc else "жоқ", None, "«Дәлдікті тексеру» бөлімінен")], accent_first=True)
    tab1, tab2, tab3, tab4 = st.tabs(["Сценарийлер", "Сезімталдық (торнадо)", "Монте-Карло", "Белгісіздік көздері"])

    # ---------- Сценарии ----------
    with tab1:
        _scenarios_tab(c, run, P, eps, pols)
    with tab2:
        _tornado_tab(c, run, P, eps, pols)
    with tab3:
        _mc_tab(c, run, mc)
    with tab4:
        _var_tab(c, run, P, eps, pols)


def _scenarios_tab(c, run, P, eps, pols):
    formulas([("Low", r"M_{low}=\sum_j N_j(1-\varepsilon)\cdot 0{,}9L\cdot\frac{c_j^{low}}{100}\cdot k_j^{low}"),
              ("High", r"M_{high}=\sum_j N_j(1+\varepsilon)\cdot 1{,}1L\cdot\frac{c_j^{high}}{100}\cdot k_j^{high}")])
    sc = scenarios(run, P, eps, pols)
    df = pd.DataFrame({LEVEL_KZ[k]: v for k, v in sc.items()}).T
    df.columns = [f"{x}, кг/сағ" for x in df.columns]
    st.dataframe(df.map(lambda v: fmt(v, 3)), width="stretch")
    df.to_csv(run["dir"] / "uncertainty_scenarios.csv", encoding="utf-8-sig")


def _tornado_tab(c, run, P, eps, pols):
    note("Бір параметрді low → high аралығында өзгертеміз, қалғандары base мәнде қалады. "
         "Ең ұзын жолақ — нәтижеге ең көп әсер ететін фактор.")
    pol = st.segmented_control("Көрсеткіш", ["CO2", *pols], default="CO2") or "CO2"
    rows = tornado(c, run, P, eps, pol)
    show_fig(tornado_fig(rows, pol, "кг/сағ"), run, f"tornado_{pol}")
    st.dataframe(pd.DataFrame(rows, columns=["Фактор", "Төмен", "Жоғары", "Base"]).assign(
        **{"Ауқым": lambda d: d["Жоғары"] - d["Төмен"]}).iloc[::-1].round(4), hide_index=True, width="stretch")


def _mc_tab(c, run, mc):
    n = c["uncertainty"]["mc_runs"]
    formulas([("Үшбұрышты таралу (a = low, m = base, b = high)",
               r"f(x)=\begin{cases}\frac{2(x-a)}{(b-a)(m-a)}, & a\le x\le m\\[2pt]"
               r"\frac{2(b-x)}{(b-a)(b-m)}, & m<x\le b\end{cases}"),
              (f"{n:,} рет қайталау".replace(",", " "),
               r"M^{(i)}=\sum_j N_j^{(i)} L^{(i)}\frac{c_j^{(i)}}{100}k_j^{(i)},\quad i=1,\dots,"
               + str(n) + r";\qquad P_5,\ P_{50},\ P_{95}")])
    st.caption("Кездейсоқ алынатындар: N (±ε), түрлер үлесі (қате матрицасы), отын шығыны, k, EF, L ±10%. "
               "Отын түрі тұрақты.")
    stats_ = pd.DataFrame({p: mc_stats(v) for p, v in mc.items()}).T
    stats_.columns = [f"{x}, кг/сағ" for x in stats_.columns]
    st.dataframe(stats_.map(lambda v: fmt(v, 4)), width="stretch")
    stats_.to_csv(run["dir"] / "monte_carlo_stats.csv", encoding="utf-8-sig")
    fig, axs = plt.subplots(1, len(mc), figsize=(4 * len(mc), 3.6))
    for ax, (p, v) in zip(axs, mc.items()):
        ax.hist(v, bins=50, color=PALETTE[0], alpha=0.85)
        for q, ls in [(5, "--"), (50, "-"), (95, "--")]:
            ax.axvline(np.percentile(v, q), color=PALETTE[1], ls=ls, lw=1.2)
        ax.set_title(f"{p}, кг/сағ")
        ax.set_ylabel("жиілік")
    fig.suptitle("Монте-Карло таралуы (үзік сызық — 5 және 95 перцентиль, тұтас — медиана)")
    fig.tight_layout()
    show_fig(fig, run, "monte_carlo")


def _var_tab(c, run, P, eps, pols):
    formulas([(None, r"w_{\text{тану}}=\frac{\mathrm{Var}(M\mid\text{тек тану})}{\mathrm{Var}(M\mid\text{тек тану})+"
                     r"\mathrm{Var}(M\mid\text{тек жорамал})}\cdot 100\%")])
    vs = variance_shares(c, run, P, eps, pols)
    vdf = pd.DataFrame(vs, index=["Тану қателігі (N, үлестер)", "Жорамалдар (шығын, k, EF, L)"]).T
    st.dataframe(vdf.round(1).map(lambda v: f"{v:.1f}%"), width="stretch")
    fig, ax = plt.subplots(figsize=(9, 3.5))
    y = np.arange(len(vdf))
    ax.barh(y, vdf.iloc[:, 0], color=PALETTE[0], label=vdf.columns[0])
    ax.barh(y, vdf.iloc[:, 1], left=vdf.iloc[:, 0], color=PALETTE[1], label=vdf.columns[1])
    ax.set_yticks(y, vdf.index)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Дисперсиядағы үлесі, %")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False)
    ax.set_title("Шашыраңқылық неден туындайды?")
    ax.grid(axis="y", alpha=0)
    fig.tight_layout()
    show_fig(fig, run, "variance_shares")
    vdf.to_csv(run["dir"] / "variance_shares.csv", encoding="utf-8-sig")
    st.caption("Әдіс: Монте-Карлоны екі рет қайталаймыз — тек тану қателігі өзгереді / тек жорамалдар өзгереді; "
               "дисперсиялардың қатынасы үлесті береді (бірінші ретті жуықтау).")
