"""«Ағын статистикасы» — статистика потока: среднее, дисперсия, Пуассон, χ², сравнение видео."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.analysis import interval_counts, load_run
from core.common import PALETTE
from core.flowstats import basic, conclusion_kz, poisson_test
from views.state import cfg, current_run, fmt, run_names, show_fig
from views.ui import formulas, header, kpis, note


def render():
    c = cfg()
    run = current_run()
    s = run["summary"]
    header("Ағын статистикасы", "Көліктер кездейсоқ (Пуассон заңымен) өте ме, әлде бағдаршам әсерінен топ-топ болып "
           "өте ме? 30 секундтық аралықтар бойынша тексереміз.", "Математика")

    df = interval_counts(run["events"], s["from_s"], s["to_s"], 30)
    df = df[df["length_s"] >= 29.9]                      # неполный последний интервал не берём
    x = df["total"].values
    b = basic(x)
    t = poisson_test(x) if b["n"] >= 5 else None
    kpis([("Аралықтар саны n", b["n"], "× 30 с"), ("Орташа x̄", fmt(b["mean"], 2), "көлік"),
          ("Дисперсия s²", fmt(b["var"], 2)), ("Дисперсия индексі ID", fmt(b["ID"], 2), None, "Пуассон үшін ≈ 1"),
          ("p-мәні (χ²)", fmt(t["p"], 4) if t and not np.isnan(t["p"]) else None)], accent_first=False)

    tab1, tab2, tab3 = st.tabs(["Сипаттамалық статистика", "Пуассон және χ²", "Бейнелерді салыстыру"])
    with tab1:
        formulas([("Орташа", r"\bar{x}=\frac{1}{n}\sum_{i=1}^{n}x_i"),
                  ("Түзетілген дисперсия", r"s^2=\frac{1}{n-1}\sum_{i=1}^{n}(x_i-\bar{x})^2"),
                  ("Дисперсия индексі", r"ID=\frac{s^2}{\bar{x}}")])
        st.markdown("**Сандарды қою**")
        st.latex(rf"\bar{{x}}=\frac{{{int(x.sum())}}}{{{b['n']}}}={b['mean']:.3f},\qquad s^2={b['var']:.3f},"
                 rf"\qquad ID=\frac{{{b['var']:.3f}}}{{{b['mean']:.3f}}}={b['ID']:.2f}")
        note("ID ≈ 1 — кездейсоқ (пуассондық) ағын; ID > 1 — көліктер топтасып өтеді (бағдаршам); "
             "ID < 1 — ағын біркелкі.")
        fig, ax = plt.subplots(figsize=(10, 3.2))
        ax.plot(df["from_s"] / 60, x, "o-", color=PALETTE[0], ms=4)
        ax.axhline(b["mean"], color=PALETTE[1], ls="--", label=f"x̄ = {b['mean']:.2f}")
        ax.fill_between(df["from_s"] / 60, b["mean"] - np.sqrt(b["var"]), b["mean"] + np.sqrt(b["var"]),
                        color=PALETTE[1], alpha=0.12, label="x̄ ± s")
        ax.set_xlabel("Уақыт, мин")
        ax.set_ylabel("Көлік / 30 с")
        ax.set_title("30 секундтық аралықтардағы көлік саны")
        ax.legend()
        fig.tight_layout()
        show_fig(fig, run, "intervals_30s")

    with tab2:
        if t is None:
            st.warning("Аралықтар тым аз (5-тен кем). Ұзағырақ бейне керек.")
        else:
            formulas([("Пуассон таралуы (λ = x̄)", r"P(X=k)=\frac{\lambda^k e^{-\lambda}}{k!}"),
                      ("Күтілетін жиілік", r"E_k = n\cdot P(X=k)"),
                      ("Пирсон критерийі", r"\chi^2=\sum_i\frac{(O_i-E_i)^2}{E_i},\qquad df = m-1-1")])
            ks = np.arange(len(t["obs"]))
            fig, ax = plt.subplots(figsize=(10, 3.8))
            ax.bar(ks, t["obs"], color=PALETTE[0], alpha=0.85, label="Бақыланған O")
            ax.plot(ks, t["exp"], "o-", color=PALETTE[1], label=f"Пуассон E (λ = {t['lambda']:.2f})")
            ax.set_xlabel("30 с ішіндегі көлік саны, k")
            ax.set_ylabel("Аралықтар саны")
            ax.set_title("Гистограмма және Пуассон таралуы")
            ax.legend()
            fig.tight_layout()
            show_fig(fig, run, "poisson")
            a, b2 = st.columns([1, 1])
            a.dataframe(t["table"], hide_index=True, width="stretch")
            with b2:
                st.latex(rf"\chi^2 = {t['chi2']:.2f},\quad df = {t['df']}")
                if not np.isnan(t["chi2_crit"]):
                    st.latex(rf"\chi^2_{{0.95}}({t['df']}) = {t['chi2_crit']:.2f}")
                    st.latex(rf"p = {t['p']:.4f}")
                st.caption("Ұяшықтар күтілетін жиілік ≥ 5 болғанша біріктіріледі.")
            concl = conclusion_kz(b, t)
            note("<b>Қорытынды.</b> " + concl, "✓")
            pd.DataFrame([{**b, "chi2": t["chi2"], "df": t["df"], "p": t["p"], "conclusion": concl}]).to_csv(
                run["dir"] / "flow_stats.csv", index=False, encoding="utf-8-sig")

    with tab3:
        formulas([(None, r"\bar{q}=\frac{60}{m}\sum_{j=1}^{m}x^{(1\,\text{мин})}_j,\qquad CV=\frac{s}{\bar{q}}\cdot 100\%")])
        names = st.multiselect("Бейнелер", run_names(), default=run_names())
        rows = []
        for nm in names:
            r = load_run(c, nm)
            ss = r["summary"]
            m = interval_counts(r["events"], ss["from_s"], ss["to_s"], 60)
            m = m[m["length_s"] >= 59.9]
            ph = m["total"].values * 60.0                      # каждая минута → «в час»
            if len(ph) == 0:
                continue
            mean, sd = ph.mean(), (ph.std(ddof=1) if len(ph) > 1 else 0.0)
            rows.append({"Бейне": nm, "Ұзақтығы, мин": ss["duration_s"] / 60, "Орташа, көлік/сағ": mean,
                         "Стандартты ауытқу": sd, "CV, %": sd / mean * 100 if mean else np.nan})
        if rows:
            cdf = pd.DataFrame(rows)
            st.dataframe(cdf.round(1), hide_index=True, width="stretch")
            cdf.to_csv(run["dir"] / "videos_compare.csv", index=False, encoding="utf-8-sig")
            fig, ax = plt.subplots(figsize=(8, 3.6))
            ax.bar(cdf["Бейне"], cdf["Орташа, көлік/сағ"], yerr=cdf["Стандартты ауытқу"], capsize=6, color=PALETTE[0])
            ax.set_ylabel("көлік/сағ")
            ax.set_title("Бейнелер бойынша орташа ағын (± s)")
            fig.tight_layout()
            show_fig(fig, run, "videos_compare")
