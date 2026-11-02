"""Раздел 7. «Сценарийлер» — автобус вместо машины."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.analysis import counts_by_class
from core.common import PALETTE
from core.scenarios import per_passenger, run_scenario
from views.state import cfg, current_run, fmt, params, show_fig
from views.ui import formulas, header, kpis, note


def render():
    c = cfg()
    run = current_run()
    P = params()
    sc = c["scenario"]
    pols = c["pollutants_main"]
    header("Сценарийлер: автобус жеңіл көліктің орнына", "Жеңіл көлік сапарларының p үлесі автобусқа ауысса, "
           "шығарындылар қалай өзгереді? Есептеу сағатына, көлік түрлері бойынша.", "Математика")

    # ---------- Параметры ----------
    a, b, d = st.columns(3)
    occ = a.number_input("Жеңіл көліктің орташа толуы, адам", 1.0, 5.0, float(sc["car_occupancy"]["base"]), 0.05,
                         help=sc["car_occupancy"]["source"])
    cap = b.number_input("Автобус сыйымдылығы, адам", 10, 200, int(sc["bus_capacity"]["base"]),
                         help=sc["bus_capacity"]["source"])
    occ_bus = d.number_input("Автобустың орташа толуы, адам", 1.0, 200.0, float(sc["bus_occupancy"]["base"]), 0.5,
                             help=sc["bus_occupancy"]["source"])
    with st.expander("Параметрлердің дереккөздері"):
        for k_, name in [("car_occupancy", "Жеңіл көлік толуы"), ("bus_capacity", "Автобус сыйымдылығы"),
                         ("bus_occupancy", "Автобус толуы")]:
            v = sc[k_]
            st.markdown(f"- **{name}** (low {v['low']}, base {v['base']}, high {v['high']}): {v['source']}")

    p = st.slider("p — ауысқан сапарлар үлесі, %", 0, 100, 20) / 100

    # ---------- Сценарии А и Ә ----------
    r = run_scenario(run, P, p, occ, cap, pols)
    rA = next(x for x in r["rows"] if x["Көрсеткіш"] == "CO2" and x["Сценарий"] == "А")
    rB = next(x for x in r["rows"] if x["Көрсеткіш"] == "CO2" and x["Сценарий"] == "Ә")
    kpis([("CO2 азаюы, А", fmt(rA["r, %"], 1), "%", f"−{fmt(rA['ΔM'], 1)} кг/сағ"),
          ("CO2 азаюы, Ә", fmt(rB["r, %"], 1), "%", f"−{fmt(rB['ΔM'], 1)} кг/сағ"),
          ("Ағыннан алынған жеңіл көлік", fmt(r["removed_cars"], 1), "/сағ"),
          ("Ауысқан жолаушы", fmt(r["passengers"], 1), "/сағ"),
          ("Ә: қосымша автобус", r["extra_buses"], "/сағ")], accent_first=True)
    formulas([("Ауысқан жолаушылар және қосымша автобустар",
               r"P = p\cdot N_{car}\cdot n_{car} = " + f"{p:.2f}" + r"\cdot" + f"{counts_by_class(run)['car'] * 3600 / run['summary']['duration_s']:.1f}"
               + r"\cdot" + f"{occ:.2f}" + f" = {r['passengers']:.1f}" + r",\qquad N_{bus}^{+}=\left\lceil\frac{P}{C_{bus}}"
               r"\right\rceil=\left\lceil\frac{" + f"{r['passengers']:.1f}" + "}{" + f"{cap}" + r"}\right\rceil="
               + f"{r['extra_buses']}"),
              ("А — қосымша рейссіз; Ә — қосымша автобустармен",
               r"\Delta M = M_{\text{баст}} - M_{\text{сцен}},\qquad r = \frac{\Delta M}{M_{\text{баст}}}\cdot 100\%"),
              ("CO2 үшін, А сценарийі",
               rf"r = \frac{{{rA['Бастапқы']:.1f} - {rA['Сценарий мәні']:.1f}}}{{{rA['Бастапқы']:.1f}}}\cdot 100\% = "
               rf"{rA['r, %']:.1f}\%")])
    df = pd.DataFrame(r["rows"])
    st.dataframe(df.round(4), hide_index=True, width="stretch")
    df.to_csv(run["dir"] / "scenario_current.csv", index=False, encoding="utf-8-sig")

    # Готовые точки 0/10/20/30/50%
    st.subheader("Дайын нүктелер: " + " / ".join(f"{x}%" for x in sc["preset_points"]))
    pts = []
    for pp in sc["preset_points"]:
        rr = run_scenario(run, P, pp / 100, occ, cap, pols)
        for row in rr["rows"]:
            pts.append({"p, %": pp, **row, "Қосымша автобус": rr["extra_buses"]})
    pdf = pd.DataFrame(pts)
    piv = pdf.pivot_table(index="p, %", columns=["Көрсеткіш", "Сценарий"], values="r, %")
    st.dataframe(piv.round(2))
    pdf.to_csv(run["dir"] / "scenario_points.csv", index=False, encoding="utf-8-sig")
    fig, axs = plt.subplots(1, len(pols) + 1, figsize=(4 * (len(pols) + 1), 3.6))
    for ax, q in zip(axs, ["CO2", *pols]):
        for i, s_ in enumerate(["А", "Ә"]):
            v = pdf[(pdf["Көрсеткіш"] == q) & (pdf["Сценарий"] == s_)]
            ax.plot(v["p, %"], v["r, %"], "o-", color=PALETTE[i], label=f"{s_} сценарийі")
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_title(f"{q}: r, %")
        ax.set_xlabel("p, %")
    axs[0].legend(fontsize=8)
    fig.suptitle("Шығарындылардың азаюы r, % (ауысу үлесі p бойынша)")
    fig.tight_layout()
    show_fig(fig, run, "scenario_points")

    # ---------- Точка безубыточности ----------
    st.subheader("Пайдалылық шегі: автобустың ең аз толуы n*")
    pp = per_passenger(P, occ)
    st.markdown("Бір жолаушыға шаққандағы CO2 (1 км үшін):")
    st.latex(r"e_{car}=\frac{c_{car}/100\cdot k_{car}}{n_{car}},\qquad e_{bus}(n)=\frac{c_{bus}/100\cdot k_{bus}}{n}")
    st.latex(r"e_{bus}(n)<e_{car}\iff \frac{c_{bus}k_{bus}}{n}<\frac{c_{car}k_{car}}{n_{car}}\iff "
             r"n>n^{*}=\frac{c_{bus}\,k_{bus}\,n_{car}}{c_{car}\,k_{car}}")
    car, bus = P["cat"]["car"], P["cat"]["bus"]
    st.latex(rf"n^{{*}}=\frac{{{bus['c'][1]:.2f}\cdot{P['k'][bus['fuel']][1]:.3f}\cdot{occ:.2f}}}"
             rf"{{{car['c'][1]:.2f}\cdot{P['k'][car['fuel']][1]:.3f}}}\approx{pp['n_star']:.1f}\ \text{{адам}}")
    kpis([("n* — пайдалылық шегі", f"{pp['n_star']:.1f}", "адам"),
          ("Жеңіл көлік", f"{pp['e_car_pkm'] * 1000:.0f}", "г CO2 / жолаушы-км"),
          (f"Автобус ({occ_bus:g} адам)", f"{pp['e_bus_vkm'] / occ_bus * 1000:.0f}", "г CO2 / жолаушы-км")])
    n = np.linspace(1, cap, 300)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(n, pp["e_bus_vkm"] / n * 1000, color=PALETTE[1], label="Автобус")
    ax.axhline(pp["e_car_pkm"] * 1000, color=PALETTE[0], label=f"Жеңіл көлік (n = {occ:g})")
    ax.axvline(pp["n_star"], color="gray", ls="--", label=f"n* ≈ {pp['n_star']:.1f}")
    ax.axvline(occ_bus, color=PALETTE[2], ls=":", label=f"Автобустың орташа толуы ({occ_bus:g})")
    ax.set_yscale("log")
    ax.set_xlabel("Автобустағы жолаушылар саны n")
    ax.set_ylabel("CO2, г / жолаушы-км (лог. шкала)")
    ax.set_title("Бір жолаушыға шаққандағы CO2: автобус vs жеңіл көлік")
    ax.legend(fontsize=9)
    fig.tight_layout()
    show_fig(fig, run, "break_even")
    verdict = ("тиімдірек" if occ_bus > pp["n_star"] else "тиімсіз")
    note(f"Автобустың орташа толуы {occ_bus:g} адам, n* ≈ {pp['n_star']:.1f}: автобус бір жолаушыға шаққанда "
         f"жеңіл көліктен <b>{verdict}</b>.", "✓")
