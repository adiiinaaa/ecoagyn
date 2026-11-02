"""Таблицы и графики по результатам подсчёта (раздел 1) и загрузка результатов."""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.common import CLASS_COLORS, CLASS_ORDER, class_kz, results_dir, save_fig


def load_run(cfg, name):
    """Все сохранённые данные одного видео."""
    out = results_dir(cfg, name)
    run = {"dir": out, "name": name}
    with open(out / "summary.json", encoding="utf-8") as f:
        run["summary"] = json.load(f)
    run["events"] = pd.read_csv(out / "events.csv")
    p = out / "labels.csv"
    run["labels"] = pd.read_csv(p) if p.exists() else None
    p = out / "manual_counts.json"
    run["manual"] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    p = out / "accuracy.json"
    run["accuracy"] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return run


def annotated_video(run):
    """Видео с рамками: полное (annotated.mp4) или сжатое для онлайн-версии (annotated_web.mp4)."""
    for name in ("annotated.mp4", "annotated_web.mp4"):
        p = run["dir"] / name
        if p.exists():
            return p
    return run["dir"] / "annotated.mp4"


def interval_counts(events, start, end, width):
    """Сколько машин каждого класса в каждом интервале длиной width секунд."""
    n = int(np.ceil((end - start) / width - 1e-9))
    rows = []
    for i in range(n):
        lo, hi = start + i * width, min(start + (i + 1) * width, end)
        part = events[(events.time_s >= lo) & (events.time_s < hi)]
        row = {"interval": i + 1, "from_s": round(lo, 1), "to_s": round(hi, 1),
               "length_s": round(hi - lo, 1)}
        for c in CLASS_ORDER:
            row[c] = int((part["class"] == c).sum())
        row["total"] = int(len(part))
        rows.append(row)
    return pd.DataFrame(rows)


def summary_table(cfg, run):
    """Таблица по типам и направлениям + пересчёт на час."""
    s = run["summary"]
    per_hour = 3600 / s["duration_s"]
    d1, d2 = s["direction_names"]
    rows = []
    for c in CLASS_ORDER:
        n1, n2 = s["counts"][c]["1"], s["counts"][c]["2"]
        rows.append({"Түрі": class_kz(cfg, c), "class": c, d1: n1, d2: n2, "Барлығы": n1 + n2,
                     "Сағатына": round((n1 + n2) * per_hour, 1)})
    df = pd.DataFrame(rows)
    tot = {"Түрі": "БАРЛЫҒЫ", "class": "total", d1: df[d1].sum(), d2: df[d2].sum(),
           "Барлығы": df["Барлығы"].sum(), "Сағатына": round(df["Барлығы"].sum() * per_hour, 1)}
    return pd.concat([df, pd.DataFrame([tot])], ignore_index=True)


def counts_by_class(run):
    """N_j — посчитано машин каждого класса за видео."""
    s = run["summary"]
    return {c: s["counts"][c]["1"] + s["counts"][c]["2"] for c in CLASS_ORDER}


def chart_intervals(cfg, df, width, title):
    """Столбчатая диаграмма по интервалам (стопкой по классам)."""
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(df))
    bottom = np.zeros(len(df))
    for c in CLASS_ORDER:
        ax.bar(x, df[c], bottom=bottom, color=CLASS_COLORS[c], label=class_kz(cfg, c), width=0.85)
        bottom += df[c].values
    step = max(1, len(df) // 20)
    lab = [f"{int(v // 60)}:{int(v % 60):02d}" for v in df["from_s"]]
    ax.set_xticks(x[::step], lab[::step], rotation=0)
    ax.set_xlabel("Бейне уақыты (мин:сек)")
    ax.set_ylabel(f"Көлік саны / {width} с")
    ax.set_title(title)
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False)
    fig.tight_layout()
    return fig


def save_count_tables(cfg, out):
    """Сохраняет таблицы и графики раздела 1 в results/<видео>/."""
    out = Path(out)
    run = load_run(cfg, out.name)
    s, ev = run["summary"], run["events"]
    start, end = s["from_s"], s["to_s"]
    summary_table(cfg, run).to_csv(out / "summary_table.csv", index=False, encoding="utf-8-sig")
    for width, name, title in [(30, "per_30s", "Әр 30 секундтағы көлік саны"),
                               (60, "per_minute", "Әр минуттағы көлік саны")]:
        df = interval_counts(ev, start, end, width)
        df.to_csv(out / f"{name}.csv", index=False, encoding="utf-8-sig")
        fig = chart_intervals(cfg, df, width, title)
        save_fig(fig, out / "png" / f"{name}.png")
        plt.close(fig)
