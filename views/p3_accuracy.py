"""«Дәлдікті тексеру» — проверка точности подсчёта и типа транспорта."""
import base64
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core.analysis import annotated_video
from views.p1_video import cloud_mode
from core.accuracy import NOT_VEHICLE, confusion, count_error, evaluate, metrics
from core.common import CLASS_ORDER, class_kz
from views.state import cfg, current_run, fmt, show_fig
from views.ui import formulas, header, kpis, note


def heatmap(m, title, labeler):
    fig, ax = plt.subplots(figsize=(1.1 * len(m.columns) + 2.5, 0.8 * len(m.index) + 1.8))
    ax.imshow(m.values, cmap="Greens")
    ax.set_xticks(range(len(m.columns)), [labeler(x) for x in m.columns], rotation=30, ha="right")
    ax.set_yticks(range(len(m.index)), [labeler(x) for x in m.index])
    for i in range(len(m.index)):
        for j in range(len(m.columns)):
            v = m.values[i, j]
            ax.text(j, i, int(v), ha="center", va="center",
                    color="white" if v > m.values.max() * 0.6 else "#182522", fontsize=10)
    ax.set_xlabel("Бағдарлама болжамы")
    ax.set_ylabel("Шын мәні (қолмен)")
    ax.set_title(title)
    ax.grid(False)
    fig.tight_layout()
    return fig


def _img_uri(path):
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def _lab(c, x):
    return class_kz(c, x) if x != NOT_VEHICLE else "көлік емес"


def render():
    c = cfg()
    run = current_run()
    s = run["summary"]
    acc = run["accuracy"] or {}
    header("Дәлдікті тексеру", "Бағдарлама нәтижесін қолмен санаумен салыстырамыз. ε және қате матрицасы "
           "«Белгісіздік» бөлімінде автоматты түрде қолданылады.", "Талдау",
           ("Тексерілді", "ok") if acc.get("eps_total_pct") is not None else ("Тексерілмеген", "wait"))
    kpis([("Санау қателігі ε", fmt(acc.get("eps_total_pct"), 1) if acc.get("eps_total_pct") is not None else None, "%"),
          ("Көлік түрінің дәлдігі", fmt(acc["class_accuracy"] * 100, 1) if acc.get("class_accuracy") is not None
           and not np.isnan(acc["class_accuracy"]) else None, "%"),
          ("Белгіленген кескін", acc.get("n_labeled"), "дана")])

    tab_a, tab_b = st.tabs(["Қолмен санау және ε", "Көлік түрін тексеру"])

    # ---------- A. Ручной подсчёт ----------
    with tab_a:
        formulas([("Салыстырмалы қателік", r"\varepsilon = \frac{|N_{\text{прог}} - N_{\text{қол}}|}{N_{\text{қол}}}"
                                         r"\cdot 100\%")])
        man = run["manual"] or {"from_s": s["from_s"], "to_s": min(s["to_s"], s["from_s"] + 300), "counts": {}}
        a, b = st.columns(2)
        fr = a.number_input("Кесінді басы, с", float(s["from_s"]), float(s["to_s"]), float(man["from_s"]), 1.0)
        to = b.number_input("Кесінді соңы, с", float(s["from_s"]), float(s["to_s"]), float(man["to_s"]), 1.0)
        v = annotated_video(run)
        if v.exists():
            with st.expander("Санау үшін бейнені ашу"):
                st.video(str(v), start_time=int(fr))
        cols = st.columns(4)
        counts = {cl: cols[i].number_input(f"{class_kz(c, cl)}", 0, 100000, int(man["counts"].get(cl, 0)))
                  for i, cl in enumerate(CLASS_ORDER)}
        if st.button("Сақтау және есептеу", type="primary", icon=":material/calculate:", disabled=cloud_mode(),
                     help="Тек компьютердегі нұсқада" if cloud_mode() else None):
            man = {"from_s": fr, "to_s": to, "counts": counts}
            (run["dir"] / "manual_counts.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), "utf-8")
            run["manual"] = man
            evaluate(run)
            st.rerun()
        if run["manual"]:
            ce = count_error(run, run["manual"])
            ce.to_csv(run["dir"] / "count_error.csv", index=False, encoding="utf-8-sig")
            tot = ce.iloc[-1]
            if tot["N_manual"] > 0:
                st.markdown("**Есептеу**")
                st.latex(rf"\varepsilon = \frac{{|{int(tot['N_prog'])} - {int(tot['N_manual'])}|}}"
                         rf"{{{int(tot['N_manual'])}}}\cdot 100\% = {tot['eps_pct']:.1f}\%")
            ce["Түрі"] = ce["class"].map(lambda x: class_kz(c, x) if x != "total" else "БАРЛЫҒЫ")
            ce["ε, %"] = ce["eps_pct"].map(lambda x: fmt(x, 1) if pd.notna(x) else "—")
            st.dataframe(ce[["Түрі", "N_prog", "N_manual", "ε, %"]].rename(
                columns={"N_prog": "N бағдарлама", "N_manual": "N қолмен"}), hide_index=True, width="stretch")

    # ---------- B. Разметка типа транспорта ----------
    with tab_b:
        ev = run["events"]
        ev = ev[ev["crop"].notna()] if "crop" in ev else ev.iloc[0:0]
        ev = ev[[(run["dir"] / "crops" / str(x)).exists() for x in ev["crop"]]]   # в онлайн-версии кескіндер жоқ
        if ev.empty:
            st.info("Кескіндер жоқ: бұл тексеру тек компьютердегі нұсқада қолжетімді.")
            return
        note(f"Әр кескін үшін дұрыс көлік түрін таңдаңыз. «{_lab(c, NOT_VEHICLE)}» — қате анықталған объект "
             "немесе қайталанған көлік. Бос жолдар есепке алынбайды.")
        lab_path = run["dir"] / "labels.csv"
        labels = run["labels"] if run["labels"] is not None else pd.DataFrame(columns=["track_id", "true_class"])
        labels = labels[["track_id", "true_class"]] if "true_class" in labels else labels
        ev = ev.assign(n=ev["n"] if "n" in ev else range(1, len(ev) + 1))   # № как на видео
        df = ev[["n", "track_id", "crop", "class"]].merge(labels, on="track_id", how="left")
        batch = 25
        n_pages = max(1, (len(df) - 1) // batch + 1)
        page = st.number_input(f"Топ (барлығы {n_pages}, әрқайсында {batch})", 1, n_pages, 1)
        part = df.iloc[(page - 1) * batch: page * batch].copy()
        part["img"] = [_img_uri(run["dir"] / "crops" / p) for p in part["crop"]]
        part["pred"] = part["class"].map(lambda x: class_kz(c, x))
        opts = CLASS_ORDER + [NOT_VEHICLE]
        ed = st.data_editor(
            part[["img", "n", "track_id", "pred", "true_class"]],
            column_config={
                "img": st.column_config.ImageColumn("Кескін", width="medium"),
                "n": st.column_config.NumberColumn("№", disabled=True),
                "track_id": None,
                "pred": st.column_config.TextColumn("Бағдарлама", disabled=True),
                "true_class": st.column_config.SelectboxColumn("Дұрыс түрі", options=opts),
            }, hide_index=True, row_height=90, width="stretch", key=f"ed::{run['name']}::{page}")
        b1, b2 = st.columns(2)
        if b1.button("Бос жолдарға болжамды көшіру", icon=":material/content_copy:", width="stretch",
                     disabled=cloud_mode()):
            p2 = part.copy()
            p2["true_class"] = p2["true_class"].fillna(p2["class"])
            _save_labels(labels, p2, lab_path)
            st.rerun()
        if b2.button("Белгілерді сақтау", type="primary", icon=":material/save:", width="stretch",
                     disabled=cloud_mode()):
            _save_labels(labels, ed, lab_path)
            run["labels"] = pd.read_csv(lab_path)
            evaluate(run)
            st.rerun()

        lab = run["labels"]
        if lab is None or lab["true_class"].isna().all():
            return
        evaluate(run)
        evi = run["events"].set_index("track_id")
        L = lab.dropna(subset=["true_class"])
        L = L[L["track_id"].isin(evi.index)]
        m = confusion(L["true_class"], evi.loc[L["track_id"], "class"].values, CLASS_ORDER + [NOT_VEHICLE])
        st.subheader("Қате матрицасы")
        show_fig(heatmap(m, "Көлік түрі: қате матрицасы", lambda x: _lab(c, x)), run, "confusion_class")
        formulas([(None, r"Precision=\frac{TP}{TP+FP},\quad Recall=\frac{TP}{TP+FN},\quad "
                         r"F_1=\frac{2\cdot P\cdot R}{P+R},\quad Accuracy=\frac{\sum_i TP_i}{N}")])
        a_, mt = metrics(m.loc[CLASS_ORDER, CLASS_ORDER])
        mt.to_csv(run["dir"] / "metrics_class.csv", index=False, encoding="utf-8-sig")
        st.dataframe(mt.assign(**{"class": mt["class"].map(lambda x: class_kz(c, x))}).round(3),
                     hide_index=True, width="stretch")


def _save_labels(old, edited, path):
    """Новые метки заменяют старые для тех же track_id."""
    new = edited[["track_id", "true_class"]].dropna(subset=["true_class"])
    keep = old[~old["track_id"].isin(edited["track_id"])] if len(old) else old
    pd.concat([keep, new], ignore_index=True).to_csv(path, index=False, encoding="utf-8")
