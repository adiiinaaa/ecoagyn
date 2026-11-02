"""«Шығарындылар есебі» — топливо, CO2 и загрязнители: формулы, пошаговый расчёт, результат."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.analysis import counts_by_class
from core.common import CLASS_COLORS, PALETTE, class_kz
from core.emissions import ASSUMPTIONS_KZ, category_entry, compare_models, scale_factors
from views.state import cfg, current_run, fmt, params, reset_params, show_fig
from views.ui import formulas, header, kpis, note

PER_KZ = {"video": "бейне ішінде", "hour": "сағатына", "day": "тәулігіне", "year": "жылына (бағалау)"}


def key_kz(c, k):
    return {"total": "БАРЛЫҒЫ", "all": "Барлық көлік (орташа)"}.get(k) or class_kz(c, k)


def _params_editor(c, P):
    """Параметры: k по видам топлива и категории транспорта."""
    st.markdown("**k — 1 литр отыннан шығатын CO2, кг/л**")
    st.caption("base: EMEP/EEA Table 3-12 × тығыздық (Table 3-28); low/high: IPCC 2006, 95% аралығы.")
    kd = pd.DataFrame([{"fuel": f, "Отын": c["fuels"][f]["kz"], "low": v[0], "base": v[1], "high": v[2]}
                       for f, v in P["k"].items()])
    ked = st.data_editor(kd, column_config={"fuel": None, "Отын": st.column_config.TextColumn(disabled=True)},
                         hide_index=True, key="ed::k", width="stretch")
    for _, r in ked.iterrows():
        P["k"][r["fuel"]] = [float(r["low"]), float(r["base"]), float(r["high"])]

    st.markdown("**Көлік түрлері: отын, шығын c (л/100 км), шығарынды коэффициенттері EF (г/км)**")
    pols = c["pollutants_main"]
    rows = []
    for k, e in P["cat"].items():
        r = {"key": k, "Түрі": class_kz(c, k), "Отын": e["fuel"],
             "c low": e["c"][0], "c base": e["c"][1], "c high": e["c"][2]}
        r.update({f"{p} г/км": e["ef"][p][1] for p in pols})
        rows.append(r)
    fuels = sorted({f for k in P["cat"] for f in c["categories"][k]["fuels"]})
    col = {"key": None, "Түрі": st.column_config.TextColumn(disabled=True),
           "Отын": st.column_config.SelectboxColumn(options=fuels)}
    ed = st.data_editor(pd.DataFrame(rows), column_config=col, hide_index=True, key="ed::cat", width="stretch")
    for _, r in ed.iterrows():
        k, e = r["key"], P["cat"][r["key"]]
        if r["Отын"] != e["fuel"] and r["Отын"] in c["categories"][k]["fuels"]:
            P["cat"][k] = category_entry(c, "categories", k, r["Отын"])
            st.rerun()
        e["c"] = [float(r["c low"]), float(r["c base"]), float(r["c high"])]
        for p in pols:
            v = float(r[f"{p} г/км"])
            if abs(v - e["ef"][p][1]) > 1e-12:            # base изменили → low/high сдвигаем пропорционально
                f = v / e["ef"][p][1] if e["ef"][p][1] else 1
                e["ef"][p] = [e["ef"][p][0] * f, v, e["ef"][p][2] * f]
    with st.expander("Мәндердің дереккөзі"):
        for k, e in P["cat"].items():
            st.markdown(f"- **{class_kz(c, k)}** ({e['fuel']}, Tier 1: {e['tier1']}): {e['why']}")
    cc = st.columns(2)
    P["hours_day"] = cc[0].number_input("Тәулігіне белсенді қозғалыс, сағ", 1, 24, int(P["hours_day"]),
                                        help=c["road"]["time_source"])
    P["days_year"] = cc[1].number_input("Жылдағы күн саны", 1, 366, int(P["days_year"]))
    if st.button("Әдепкі мәндерге қайтару", icon=":material/restart_alt:"):
        reset_params()
        st.rerun()


def render():
    c = cfg()
    run = current_run()
    P = params()
    pols = c["pollutants_main"] + c["pollutants_extra"]
    header("Шығарындылар есебі", "Көлік саны → жүрілген жол → отын → CO2 және ластаушы заттар. "
           "Әр қадам формуламен және нақты сандармен көрсетілген.", "Математика")

    top = st.columns([1, 2])
    P["L"] = top[0].number_input("Учаске ұзындығы L, км", 0.01, 100.0, float(P["L"]), 0.1,
                                 help=c["road"]["segment_length_source"])
    if P["L"] == c["road"]["segment_length_km"]:
        with top[1]:
            note("L әлі әдепкі мәнде (1 км). Картадан (2GIS) бақыланатын учаскенің нақты ұзындығын енгізіңіз — "
                 "барлық шығарындылар L-ге тура пропорционал.", "⚠")

    res = compare_models(c, run, P, "base", pols)
    sf = scale_factors(run, P)
    t = res["1"].iloc[-1]
    kpis([("CO2", fmt(t["M_kg"] * sf["hour"], 1), "кг/сағ", f"тәулігіне {fmt(t['M_kg'] * sf['day'] / 1000, 2)} т"),
          ("Отын", fmt(t["Q_l"] * sf["hour"], 1), "л/сағ"),
          ("CO", fmt(t["CO_kg"] * sf["hour"], 3), "кг/сағ"),
          ("NOx", fmt(t["NOx_kg"] * sf["hour"], 3), "кг/сағ"),
          ("PM2.5", fmt(t["PM2.5_kg"] * sf["hour"] * 1000, 1), "г/сағ")], accent_first=True)

    tab1, tab2, tab3, tab4 = st.tabs(["Формулалар және қадамдық есеп", "Нәтиже кестесі", "Модельдерді салыстыру",
                                      "Параметрлер"])

    # ---------- Формулы и пошаговый расчёт ----------
    with tab1:
        formulas([
            ("1. Сағатына қайта есептеу (T — бейне ұзақтығы, с)", r"N_j^{\,сағ} = N_j\cdot\frac{3600}{T}"),
            ("2. Жүрілген жол", r"S_j = N_j^{\,сағ}\cdot L"),
            ("3. Отын (c_j — л/100 км)", r"Q_j = S_j\cdot\frac{c_j}{100}"),
            ("4. CO2 (k_j — кг CO2 / л)", r"M_j = Q_j\cdot k_j,\qquad M=\sum_j M_j"),
            ("5. Ластаушы зат (EF_j — г/км)", r"E_j = S_j\cdot EF_j\,/\,1000\ \text{[кг]},\qquad E=\sum_j E_j"),
        ])
        st.markdown("#### Қадамдық есеп (сағатына)")
        N = counts_by_class(run)
        cats = [k for k in N if N[k] > 0] or list(N)
        k = st.segmented_control("Көлік түрі", cats, default=cats[0], format_func=lambda x: class_kz(c, x)) or cats[0]
        e, T = P["cat"][k], run["summary"]["duration_s"]
        kk = P["k"][e["fuel"]][1]
        Nh = N[k] * 3600 / T
        S = Nh * P["L"]
        Q = S * e["c"][1] / 100
        M = Q * kk
        with st.container(border=True):
            st.caption(f"{class_kz(c, k)} · отын: {c['fuels'][e['fuel']]['kz']} · L = {P['L']:g} км")
            st.latex(rf"N^{{\text{{сағ}}}} = {N[k]}\cdot\frac{{3600}}{{{T:.1f}}} = {Nh:.1f}\ \text{{көлік/сағ}}")
            st.latex(rf"S = {Nh:.1f}\cdot {P['L']:g} = {S:.1f}\ \text{{км/сағ}}")
            st.latex(rf"Q = {S:.1f}\cdot\frac{{{e['c'][1]:.2f}}}{{100}} = {Q:.2f}\ \text{{л/сағ}}")
            st.latex(rf"M = {Q:.2f}\cdot {kk:.3f} = {M:.2f}\ \text{{кг CO}}_2\text{{/сағ}}")
            for p in c["pollutants_main"]:
                ef = e["ef"][p][1]
                st.latex(rf"E_{{\mathrm{{{p}}}}} = {S:.1f}\cdot {ef:.5f}\,/\,1000 = {S * ef / 1000:.4f}\ \text{{кг/сағ}}")
        st.latex(r"M = \sum_j M_j = " + " + ".join(f"{v * sf['hour']:.2f}" for v in res["1"]["M_kg"][:-1])
                 + rf" = {t['M_kg'] * sf['hour']:.2f}\ \text{{кг/сағ}}")
        st.markdown("#### Уақытқа көшу")
        st.latex(rf"M_{{\text{{тәул}}}} = M_{{\text{{сағ}}}}\cdot h = {t['M_kg'] * sf['hour']:.1f}\cdot {P['hours_day']} = "
                 rf"{t['M_kg'] * sf['day']:.0f}\ \text{{кг}},\qquad M_{{\text{{жыл}}}} = M_{{\text{{тәул}}}}\cdot {P['days_year']} = "
                 rf"{t['M_kg'] * sf['year'] / 1000:.0f}\ \text{{т (бағалау)}}")

    # ---------- Таблица результата ----------
    with tab2:
        per = st.segmented_control("Кезең", list(PER_KZ), default="hour", format_func=lambda x: PER_KZ[x]) or "hour"
        m1, f = res["1"], sf[per]
        show = pd.DataFrame({
            "Түрі": [key_kz(c, x) for x in m1["key"]],
            "Отын": [c["fuels"][x]["kz"] if x else "" for x in m1["fuel"]],
            "N": (m1["N"] * f).round(1), "S, км": (m1["S_km"] * f).round(1), "Q, л": (m1["Q_l"] * f).round(2),
            "M (CO2), кг": (m1["M_kg"] * f).round(2), **{f"{p}, кг": (m1[f"{p}_kg"] * f).round(4) for p in pols}})
        st.dataframe(show, hide_index=True, width="stretch")
        show.to_csv(run["dir"] / f"emissions_model1_{per}.csv", index=False, encoding="utf-8-sig")
        tt = pd.DataFrame({PER_KZ[x]: [t["Q_l"] * sf[x], t["M_kg"] * sf[x], *[t[f"{p}_kg"] * sf[x] for p in pols]]
                           for x in ("hour", "day", "year")},
                          index=["Отын, л", "CO2, кг", *[f"{p}, кг" for p in pols]])
        tt.to_csv(run["dir"] / "emissions_periods.csv", encoding="utf-8-sig")
        st.dataframe(tt.map(lambda v: fmt(v, 3)), width="stretch")

        fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
        keys = list(m1["key"][:-1])
        lab = [key_kz(c, x) for x in keys]
        ax[0].barh(lab[::-1], (m1["M_kg"][:-1] * sf["hour"]).values[::-1],
                   color=[CLASS_COLORS.get(x, PALETTE[0]) for x in keys][::-1])
        ax[0].set_title("CO2, кг/сағ")
        x = np.arange(len(c["pollutants_main"]))
        w = 0.8 / max(1, len(keys))
        for i, kk_ in enumerate(keys):
            ax[1].bar(x + i * w - 0.4 + w / 2, [m1[f"{p}_kg"].iloc[i] * sf["hour"] for p in c["pollutants_main"]], w,
                      label=lab[i], color=CLASS_COLORS.get(kk_, PALETTE[i]))
        ax[1].set_xticks(x, c["pollutants_main"])
        ax[1].set_yscale("log")
        ax[1].set_title("Ластаушы заттар, кг/сағ (лог. шкала)")
        ax[1].legend(fontsize=8)
        fig.tight_layout()
        show_fig(fig, run, "emissions_by_type")

    # ---------- Модели 0 и 1 ----------
    with tab3:
        note("<b>0-модель</b> — барлық көлік бір орташа бензин жеңіл көлігі деп есептеледі. "
             "<b>1-модель</b> — әр көлік түріне өз отыны, шығыны және коэффициенттері. "
             "Айырмашылық көлік құрамын ескерудің маңызын көрсетеді.")
        formulas([(None, r"\Delta = \frac{M^{(0)} - M^{(1)}}{M^{(1)}}\cdot 100\%")])
        rows = []
        for mk, df in res.items():
            r = df.iloc[-1]
            rows.append({"Модель": f"{mk}-модель", "Отын, л/сағ": r["Q_l"] * sf["hour"],
                         "CO2, кг/сағ": r["M_kg"] * sf["hour"],
                         **{f"{p}, кг/сағ": r[f"{p}_kg"] * sf["hour"] for p in c["pollutants_main"]}})
        cmp_ = pd.DataFrame(rows)
        for col_ in ["CO2, кг/сағ", *[f"{p}, кг/сағ" for p in c["pollutants_main"]]]:
            cmp_[f"Δ {col_.split(',')[0]}, %"] = (cmp_[col_] / cmp_.iloc[1][col_] - 1) * 100
        st.dataframe(cmp_.round(3), hide_index=True, width="stretch")
        cmp_.to_csv(run["dir"] / "models_compare.csv", index=False, encoding="utf-8-sig")
        fig, axs = plt.subplots(1, 4, figsize=(12, 3.2))
        for ax_, col_ in zip(axs, ["CO2, кг/сағ", *[f"{p}, кг/сағ" for p in c["pollutants_main"]]]):
            ax_.bar(["0-модель", "1-модель"], cmp_[col_], color=[PALETTE[5], PALETTE[0]])
            ax_.set_title(col_)
        fig.tight_layout()
        show_fig(fig, run, "models_compare")

    with tab4:
        _params_editor(c, P)

    st.markdown("#### Жорамалдар")
    for a_ in ASSUMPTIONS_KZ:
        st.markdown(f"- {a_}")
