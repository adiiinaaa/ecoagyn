"""Проверка точности (раздел 3).

ε = |N_прог − N_ручн| / N_ручн · 100%
Тип транспорта (YOLO): матрица ошибок, accuracy, precision, recall, F1 по классам.
Результат сохраняется в accuracy.json и автоматически используется в разделе 5.
"""
import json

import numpy as np
import pandas as pd

from core.common import CLASS_ORDER

NOT_VEHICLE = "not_vehicle"   # ложное срабатывание (не машина / дубль)


def count_error(run, manual):
    """manual = {'from_s', 'to_s', 'counts': {класс: число}}."""
    ev = run["events"]
    part = ev[(ev.time_s >= manual["from_s"]) & (ev.time_s < manual["to_s"])]
    rows = []
    for c in CLASS_ORDER:
        n_prog = int((part["class"] == c).sum())
        n_man = int(manual["counts"].get(c, 0))
        eps = abs(n_prog - n_man) / n_man * 100 if n_man > 0 else None
        rows.append({"class": c, "N_prog": n_prog, "N_manual": n_man, "eps_pct": eps})
    n_prog, n_man = len(part), sum(int(v) for v in manual["counts"].values())
    rows.append({"class": "total", "N_prog": n_prog, "N_manual": n_man,
                 "eps_pct": abs(n_prog - n_man) / n_man * 100 if n_man > 0 else None})
    return pd.DataFrame(rows)


def confusion(y_true, y_pred, labels):
    """Матрица ошибок: строки — истинный класс, столбцы — предсказанный."""
    m = pd.DataFrame(0, index=labels, columns=labels)
    for t, p in zip(y_true, y_pred):
        if t in m.index and p in m.columns:
            m.loc[t, p] += 1
    return m


def metrics(m):
    """accuracy и precision/recall/F1 по каждому классу из матрицы ошибок."""
    rows = []
    total = m.values.sum()
    for c in m.index:
        tp = m.loc[c, c]
        fp = m[c].sum() - tp
        fn = m.loc[c].sum() - tp
        prec = tp / (tp + fp) if tp + fp else np.nan
        rec = tp / (tp + fn) if tp + fn else np.nan
        f1 = 2 * prec * rec / (prec + rec) if prec and rec and not np.isnan(prec + rec) else np.nan
        rows.append({"class": c, "support": int(m.loc[c].sum()), "precision": prec, "recall": rec, "F1": f1})
    acc = np.trace(m.values) / total if total else np.nan
    return float(acc), pd.DataFrame(rows)


def evaluate(run):
    """Все метрики по разметке labels.csv (+ ручной подсчёт). Пишет accuracy.json."""
    res = {}
    if run.get("manual"):
        ce = count_error(run, run["manual"])
        tot = ce[ce["class"] == "total"].iloc[0]
        res["eps_total_pct"] = None if pd.isna(tot["eps_pct"]) else float(tot["eps_pct"])
        res["eps_by_class"] = {r["class"]: (None if pd.isna(r["eps_pct"]) else float(r["eps_pct"]))
                               for _, r in ce.iterrows()}
    lab = run.get("labels")
    if lab is not None and len(lab):
        ev = run["events"].set_index("track_id")
        lab = lab[lab["track_id"].isin(ev.index)].copy()
        lab["pred_class"] = ev.loc[lab["track_id"], "class"].values
        # Класс YOLO: P(истинный | предсказанный) — для поправки долей в разделе 5
        P = {}
        for pred, g in lab.groupby("pred_class"):
            vc = g["true_class"].value_counts(normalize=True)
            P[pred] = {k: float(v) for k, v in vc.items()}
        res["p_true_given_pred"] = P
        res["n_labeled"] = int(len(lab))
        labels = CLASS_ORDER + [NOT_VEHICLE]
        m = confusion(lab["true_class"], lab["pred_class"], labels)
        acc, mt = metrics(m.loc[CLASS_ORDER, CLASS_ORDER])
        res["class_accuracy"] = acc
    with open(run["dir"] / "accuracy.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    run["accuracy"] = res
    return res
