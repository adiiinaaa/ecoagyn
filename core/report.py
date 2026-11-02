"""Экспорт: один HTML-отчёт со всеми таблицами и графиками + zip с PNG для стенда."""
import base64
import datetime as dt
import html
import json
import subprocess
import sys
import zipfile

import pandas as pd

from core.analysis import load_run, summary_table
from core.common import ROOT, load_config
from core.ecology import conclusions_kz, equivalents, key_numbers
from core.emissions import ASSUMPTIONS_KZ, compare_models, default_params, scale_factors
from core.method import FORMULAS, LIMITATIONS_KZ, params_table

# Порядок и подписи графиков в отчёте
FIGS = [
    ("1. Бейне және санау", [("stand_frame", "Стендке арналған кадр"), ("per_minute", "Әр минуттағы көлік саны"),
                             ("per_30s", "Әр 30 секундтағы көлік саны")]),
    ("2. Дәлдікті тексеру", [("confusion_class", "Көлік түрі: қате матрицасы")]),
    ("3. Ағын статистикасы", [("intervals_30s", "30 секундтық аралықтар"), ("poisson", "Пуассон таралуымен салыстыру"),
                              ("videos_compare", "Бейнелерді салыстыру")]),
    ("4. Шығарындылар есебі", [("emissions_by_type", "Көлік түрлері бойынша шығарындылар"),
                               ("models_compare", "0- және 1-модельді салыстыру")]),
    ("5. Белгісіздік", [("tornado_CO2", "Торнадо-диаграмма (CO2)"), ("monte_carlo", "Монте-Карло"),
                        ("variance_shares", "Белгісіздік көздерінің үлесі")]),
    ("6. Сценарийлер", [("scenario_points", "Шығарындылардың азаюы"), ("break_even", "Пайдалылық шегі n*")]),
    ("7. Экологиялық қорытынды", [("co2_periods", "CO2: сағат / тәулік / жыл")]),
]

CSS = """
body{font-family:'Segoe UI',Inter,DejaVu Sans,Arial,sans-serif;max-width:1100px;margin:28px auto;padding:0 16px;color:#182522;background:#F6F8FA}
h1{color:#167D61;margin-bottom:4px}h2{color:#182522;border-bottom:2px solid #167D61;padding-bottom:6px;margin-top:40px}
h3{color:#182522}
table{border-collapse:collapse;margin:10px 0;font-size:13px;width:100%;background:#fff}
th,td{border:1px solid #E2E9E5;padding:5px 8px;text-align:left;vertical-align:top}th{background:#E8F4EE}
img{max-width:100%;border:1px solid #E2E9E5;border-radius:12px;margin:6px 0;background:#fff}figure{margin:14px 0}
figcaption{font-size:13px;color:#66756F}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.card{border:1px solid #E2E9E5;border-radius:14px;padding:12px 14px;background:#fff;color:#66756F;font-size:13px}
.card b{display:block;font-size:22px;color:#182522;margin-top:3px}.card.accent{background:#167D61;color:#D4EDE3}
.card.accent b{color:#fff}.note{color:#66756F;font-size:13px}
"""


def _img(path):
    return f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}"


def _table(df, nd=3):
    return df.to_html(index=False, float_format=lambda v: f"{v:,.{nd}f}".replace(",", " "), border=0, escape=True)


def build_report(name, session_state):
    cfg = session_state.get("cfg") or load_config()
    P = session_state.get("params") or default_params(cfg)
    run = load_run(cfg, name)
    out = run["dir"]
    (out / "params_used.json").write_text(json.dumps(P, ensure_ascii=False, indent=1), encoding="utf-8")

    # 1. Перерисовываем все графики без браузера
    subprocess.run([sys.executable, "-m", "core.headless", name, str(out / "params_used.json")],
                   cwd=str(ROOT), capture_output=True, timeout=1800)
    run = load_run(cfg, name)

    # 2. Таблицы
    s = run["summary"]
    pols = cfg["pollutants_main"] + cfg["pollutants_extra"]
    k = key_numbers(cfg, run, P)
    eq = equivalents(cfg, k["co2_year"])
    lines, rec = conclusions_kz(cfg, run, P)
    res = compare_models(cfg, run, P, "base", pols)
    sf = scale_factors(run, P)
    cmp_ = pd.DataFrame([{"Модель": f"{m}-модель","Отын, л/сағ": df.iloc[-1]["Q_l"] * sf["hour"],
                          "CO2, кг/сағ": df.iloc[-1]["M_kg"] * sf["hour"],
                          **{f"{p}, кг/сағ": df.iloc[-1][f"{p}_kg"] * sf["hour"] for p in cfg["pollutants_main"]}}
                         for m, df in res.items()])

    def csv(name_, **kw):
        p = out / name_
        return pd.read_csv(p, **kw) if p.exists() else None

    H = [f"<!doctype html><html lang='kk'><head><meta charset='utf-8'><title>EcoAgyn есебі — {html.escape(name)}</title>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         "<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css'>",
         "<script defer src='https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js'></script>",
         "<script defer src='https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js' "
         "onload='renderMathInElement(document.body,{delimiters:[{left:\"$$\",right:\"$$\",display:true}]})'></script>",
         f"<style>{CSS}</style></head><body>",
         f"<h1>🌿 EcoAgyn — есеп</h1><p>Бейне: <b>{html.escape(s['video_name'])}</b> · кесінді {s['from_s']:.0f}–"
         f"{s['to_s']:.0f} с ({s['duration_s'] / 60:.1f} мин) · L = {P['L']:g} км · жасалған күні "
         f"{dt.datetime.now():%Y-%m-%d %H:%M}</p>",
         "<p class='note'>Көлік нөмірлері танылмаған және сақталмаған; барлық кадрларда нөмірлер мен беттер бұлдырлатылған. "
         "Барлық шығарынды мәндері — есептік бағалау, ауаны тікелей өлшеу емес.</p>",
         "<h2>Негізгі көрсеткіштер</h2><div class='cards'>"]
    for lab, val in [("Көлік/сағ", f"{k['veh_h']:.0f}"), ("Отын, л/сағ", f"{k['fuel_h']:.1f}"),
                     ("CO2, кг/сағ", f"{k['co2_hour']:.1f}"), ("CO2, т/тәулік", f"{k['co2_day'] / 1000:.2f}"),
                     ("CO2, т/жыл (бағалау)", f"{k['co2_year'] / 1000:.0f}"), ("CO, кг/сағ", f"{k['CO_hour']:.3f}"),
                     ("NOx, кг/сағ", f"{k['NOx_hour']:.3f}"), ("PM2.5, г/сағ", f"{k['PM2.5_hour'] * 1000:.1f}"),
                     ("Орман, га (1 жыл)", f"{eq['forest_ha']:.0f}")]:
        cls = "card accent" if lab.startswith("CO2, кг") else "card"
        H.append(f"<div class='{cls}'>{lab}<b>{val}</b></div>")
    H.append("</div>")
    H.append("<h2>Қорытындылар</h2><ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in lines) + "</ul>")
    H.append("<h2>Ұсыныстар</h2><ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in rec) + "</ul>")

    tables = {
        "1. Бейне және санау": [("Түрлер мен бағыттар бойынша", summary_table(cfg, run).drop(columns=["class"])),
                                ("Әр минут", csv("per_minute.csv"))],
        "2. Дәлдікті тексеру": [("Санау қателігі ε", csv("count_error.csv")),
                                ("Көлік түрі: метрикалар", csv("metrics_class.csv"))],
        "3. Ағын статистикасы": [("30 с аралықтар және χ²", csv("flow_stats.csv")), ("Бейнелер", csv("videos_compare.csv"))],
        "4. Шығарындылар есебі": [("Көлік түрлері бойынша (сағатына)", csv("emissions_model1_hour.csv")),
                                  ("Сағат / тәулік / жыл", csv("emissions_periods.csv")), ("0- және 1-модель", cmp_)],
        "5. Белгісіздік": [("Сценарийлер", csv("uncertainty_scenarios.csv")), ("Монте-Карло", csv("monte_carlo_stats.csv")),
                           ("Белгісіздік көздері, %", csv("variance_shares.csv"))],
        "6. Сценарийлер": [("Дайын нүктелер", csv("scenario_points.csv"))],
    }
    for sec, figs in FIGS:
        H.append(f"<h2>{sec}</h2>")
        for cap, df in tables.get(sec, []):
            if df is not None and len(df):
                H.append(f"<h3>{cap}</h3>{_table(df)}")
        for fname, cap in figs:
            p = out / ("stand_frame.png" if fname == "stand_frame" else f"png/{fname}.png")
            if p.exists():
                H.append(f"<figure><img src='{_img(p)}' alt='{cap}'><figcaption>{cap}</figcaption></figure>")
        if sec.startswith("4."):
            H.append("<h3>Жорамалдар</h3><ul>" + "".join(f"<li>{x}</li>" for x in ASSUMPTIONS_KZ) + "</ul>")

    H.append("<h2>8. Қалай есептелді?</h2><h3>Формулалар</h3>")
    for nm, tex in FORMULAS:
        H.append(f"<p><b>{nm}</b></p><p>$${html.escape(tex)}$$</p>")
    H.append("<h3>Параметрлер және дереккөздер</h3>" + _table(params_table(cfg, P)))
    H.append("<h3>Шектеулер</h3><ul>" + "".join(f"<li>{x}</li>" for x in LIMITATIONS_KZ) + "</ul>")
    H.append("<p class='note'>EcoAgyn · YOLO11 + ByteTrack · EMEP/EEA Guidebook 2023 (Update 2026) · IPCC 2006</p>")
    H.append("</body></html>")
    html_path = out / f"report_{name}.html"
    html_path.write_text("\n".join(H), encoding="utf-8")

    # 3. Папка PNG для стенда (zip)
    zip_path = out / f"stand_png_{name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        if (out / "stand_frame.png").exists():
            z.write(out / "stand_frame.png", "stand_frame.png")
        for p in sorted((out / "png").glob("*.png")):
            z.write(p, f"png/{p.name}")
    return html_path, zip_path
