"""«Экологиялық қорытынды» — итоговые показатели, эквиваленты, выводы."""
import matplotlib.pyplot as plt
import streamlit as st

from core.common import PALETTE
from core.ecology import busiest, conclusions_kz, equivalents, key_numbers
from views.state import cfg, current_run, fmt, params, show_fig
from views.ui import formulas, header, kpis, note


def render():
    c = cfg()
    run = current_run()
    P = params()
    k = key_numbers(c, run, P)
    eq = equivalents(c, k["co2_year"])
    header("Экологиялық қорытынды", f"Бақыланған учаске (L = {P['L']:g} км) бойынша есептік бағалау: "
           "көлік ағыны ауаға қанша CO2 және ластаушы заттар шығарады.", "Экология")

    st.markdown("#### Климат: CO2")
    kpis([("CO2 сағатына", fmt(k["co2_hour"], 1), "кг"),
          ("CO2 тәулігіне", fmt(k["co2_day"] / 1000, 2), "т", f"{P['hours_day']} белсенді сағат"),
          ("CO2 жылына", fmt(k["co2_year"] / 1000, 0), "т", "есептік бағалау"),
          ("Отын сағатына", fmt(k["fuel_h"], 1), "л"),
          ("Көлік ағыны", fmt(k["veh_h"], 0), "көлік/сағ")], accent_first=True)

    st.markdown("#### Ауа сапасы: ластаушы заттар")
    kpis([("CO", f"{fmt(k['CO_hour'], 2)} / {fmt(k['CO_day'], 1)}", "кг (сағ / тәул)", "көміртек тотығы"),
          ("NOx", f"{fmt(k['NOx_hour'], 3)} / {fmt(k['NOx_day'], 2)}", "кг (сағ / тәул)", "азот оксидтері"),
          ("PM2.5", f"{fmt(k['PM2.5_hour'] * 1000, 1)} / {fmt(k['PM2.5_day'] * 1000, 0)}", "г (сағ / тәул)",
           "ұсақ қатты бөлшектер")])

    st.markdown("#### Түсінікті баламалар")
    kpis([("Орман ауданы", fmt(eq["forest_ha"], 0), "га", "жылдық CO2-ні 1 жылда сіңіреді"),
          ("Қала ағашының көшеті", fmt(eq["seedlings_10y"], 0), "дана", "жылдық CO2-ні 10 жылда сіңіреді"),
          ("Бензин көлігі", fmt(eq["car_years"], 0), "көлік", "бір жылдық шығарындысына тең")])
    e = c["equivalents"]
    formulas([(None, rf"A_{{\text{{орман}}}} = \frac{{M_{{\text{{жыл}}}}}}{{{e['forest_t_co2_per_acre_year']:.2f}\ \text{{т/акр}}}}"
                     rf"\cdot {e['acre_to_ha']}\ = \frac{{{k['co2_year'] / 1000:.0f}}}{{{e['forest_t_co2_per_acre_year']:.2f}}}"
                     rf"\cdot {e['acre_to_ha']} \approx {eq['forest_ha']:.0f}\ \text{{га}}")])
    st.caption("Дереккөз: U.S. EPA Greenhouse Gas Equivalencies Calculator (2026).")

    a, b = st.columns([3, 2], gap="large")
    with a:
        fig, ax = plt.subplots(figsize=(7, 3.4))
        vals = [k["co2_hour"], k["co2_day"], k["co2_year"]]
        ax.bar(["Сағат", "Тәулік", "Жыл (бағалау)"], [v / 1000 for v in vals], color=[PALETTE[4], PALETTE[0], "#0F5A46"])
        ax.set_yscale("log")
        ax.set_ylabel("CO2, т (лог. шкала)")
        ax.set_title("CO2: сағат / тәулік / жыл")
        for i, v in enumerate(vals):
            ax.text(i, v / 1000, f"{v / 1000:.2f} т", ha="center", va="bottom")
        fig.tight_layout()
        show_fig(fig, run, "co2_periods")
    with b:
        st.markdown("**Ең жүктелген минуттар**")
        top = busiest(run, 60, 5)
        top = top.assign(**{"Уақыт": [f"{int(x // 60)}:{int(x % 60):02d}–{int(y // 60)}:{int(y % 60):02d}"
                                      for x, y in zip(top["from_s"], top["to_s"])]})
        st.dataframe(top[["Уақыт", "total"]].rename(columns={"total": "Көлік"}), hide_index=True, width="stretch")

    lines, rec = conclusions_kz(c, run, P)
    a, b = st.columns(2, gap="large")
    with a:
        with st.container(border=True):
            st.markdown("#### Қорытындылар")
            for x in lines:
                st.markdown(f"- {x}")
    with b:
        with st.container(border=True):
            st.markdown("#### Ұсыныстар")
            for x in rec:
                st.markdown(f"- {x}")
    note("Бұл — есептеу арқылы бағалау, ауадағы концентрацияны тікелей өлшеу емес.", "ℹ")
    (run["dir"] / "conclusions.txt").write_text("\n".join(["ҚОРЫТЫНДЫЛАР", *lines, "", "ҰСЫНЫСТАР", *rec]),
                                               encoding="utf-8")
