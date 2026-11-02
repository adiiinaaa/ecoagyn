"""Формулы, таблица всех параметров с источниками, допущения (раздел 9 и отчёт)."""
import pandas as pd

from core.common import class_kz

FORMULAS = [
    ("Сағатына қайта есептеу", r"N_{\text{сағ}} = N \cdot \frac{3600}{T_{\text{бейне}}}"),
    ("Жүрілген жол", r"S_j = N_j \cdot L"),
    ("Отын", r"Q_j = N_j \cdot L \cdot \frac{c_j}{100}"),
    ("CO2", r"M_j = Q_j \cdot k_j,\qquad M=\sum_j M_j"),
    ("Ластаушы заттар", r"E_j = N_j \cdot L \cdot EF_j,\qquad E=\sum_j E_j\ (\text{г}\to\text{кг}: /1000)"),
    ("k (base)", r"k = \left(\tfrac{\text{кг CO}_2}{\text{кг отын}}\right)_{\text{EMEP/EEA T3-12}} \cdot \rho"),
    ("k (low/high)", r"k = EF_{IPCC}\left[\tfrac{\text{кг}}{\text{ТДж}}\right]\cdot NCV\left[\tfrac{\text{ТДж}}{\text{Гг}}\right]\cdot 10^{-6}\cdot\rho"),
    ("Отын шығыны", r"c\ [\text{л/100км}] = \frac{FC\ [\text{г/км}]}{\rho\ [\text{кг/л}]\cdot 1000}\cdot 100"),
    ("EF (г/км)", r"EF_{г/км} = EF_{г/кг\ отын}^{Tier1} \cdot \frac{FC\ [\text{г/км}]}{1000}"),
    ("Тәулік / жыл", r"M_{\text{тәул}} = M_{\text{сағ}}\cdot h_{\text{белс}},\qquad M_{\text{жыл}}=M_{\text{тәул}}\cdot D"),
    ("Санау қателігі", r"\varepsilon = \frac{|N_{\text{прог}}-N_{\text{қол}}|}{N_{\text{қол}}}\cdot 100\%"),
    ("Түрлер үлесін түзету", r"N^{\text{шын}}_t = \sum_p N_p \cdot P(t\mid p)"),
    ("Сапа метрикалары", r"Precision=\frac{TP}{TP+FP},\ Recall=\frac{TP}{TP+FN},\ F_1=\frac{2PR}{P+R}"),
    ("Дисперсия индексі", r"ID = \frac{s^2}{\bar{x}}"),
    ("Пуассон, χ²", r"P(k)=\frac{\lambda^k e^{-\lambda}}{k!},\quad \chi^2=\sum\frac{(O_i-E_i)^2}{E_i}"),
    ("Вариация коэффициенті", r"CV=\frac{s}{\bar{x}}\cdot 100\%"),
    ("Сценарий", r"P=p\cdot N_{car}\cdot n_{car},\quad N_{bus}^{+}=\lceil P/C_{bus}\rceil,\quad r=\frac{M_{\text{баст}}-M_{\text{сцен}}}{M_{\text{баст}}}\cdot100\%"),
    ("Пайдалылық шегі", r"n^{*}=\frac{c_{bus}\,k_{bus}\,n_{car}}{c_{car}\,k_{car}}"),
    ("Монте-Карло", r"X^{(i)}\sim \mathrm{Tri}(low,\,base,\,high),\ i=1..10\,000;\ \ P_5,\ P_{50},\ P_{95}"),
]

LIMITATIONS_KZ = [
    "Бейнеден отын түрі, қозғалтқыш класы (Euro) және көліктің жасы анықталмайды — олар санат бойынша жорамалданады.",
    "Tier 1 коэффициенттері ЕО-27 паркі (2010) бойынша есептелген; Қазақстан паркі үшін мәндер өзгеше болуы мүмкін.",
    "Отын шығыны жылдамдыққа, кептеліске, ауа температурасына тәуелді; бұл орташа мәндер.",
    "Қысқа бейнеден жылдық мәнге көшу — тек есептік бағалау (маусымдық және апталық өзгерістер ескерілмейді).",
    "Есептеу шығарынды массасын береді, ауадағы концентрацияны емес (тарау мен метеорология ескерілмейді).",
    "Сценарийлердегі толу (адам/көлік) параметрлері Еуропа/Ұлыбритания деректерінен алынған — жергілікті деректермен ауыстыру ұсынылады.",
]


def params_table(cfg, P):
    """Все параметры расчёта (текущие значения) с источниками."""
    rows = []
    src_fuel = cfg["fuels"]["_source"]
    for f, v in P["k"].items():
        rows.append({"Параметр": f"k — {cfg['fuels'][f]['kz']}", "low": v[0], "base": v[1], "high": v[2],
                     "Өлшем": "кг CO2/л", "Дереккөз": src_fuel})
        rows.append({"Параметр": f"ρ — {cfg['fuels'][f]['kz']}", "low": None,
                     "base": cfg["fuels"][f]["density_kg_per_l"], "high": None, "Өлшем": "кг/л",
                     "Дереккөз": "EMEP/EEA Guidebook 2023 (Update 2026), 1.A.3.b.i-iv, Table 3-28"})
    for k, e in P["cat"].items():
        lab = class_kz(cfg, k)
        rows.append({"Параметр": f"c — {lab} ({cfg['fuels'][e['fuel']]['kz']})", "low": e["c"][0],
                     "base": e["c"][1], "high": e["c"][2], "Өлшем": "л/100 км",
                     "Дереккөз": cfg["fc_source"] + " " + e["why"]})
        for p in cfg["pollutants_main"] + cfg["pollutants_extra"]:
            v = e["ef"][p]
            if not any(v):
                continue
            rows.append({"Параметр": f"EF {p} — {lab} ({e['fuel']}, Tier1 {e['tier1']})",
                         "low": v[0], "base": v[1], "high": v[2], "Өлшем": "г/км",
                         "Дереккөз": cfg["tier1_ef_g_per_kg_fuel"]["_source"]})
    e = P["m0"]
    rows.append({"Параметр": "c — 0-модель (бір орташа көлік)", "low": e["c"][0], "base": e["c"][1],
                 "high": e["c"][2], "Өлшем": "л/100 км", "Дереккөз": cfg["model0"]["why"]})
    rows.append({"Параметр": "L — учаске ұзындығы", "low": None, "base": P["L"], "high": None, "Өлшем": "км",
                 "Дереккөз": cfg["road"]["segment_length_source"]})
    rows.append({"Параметр": "Белсенді сағаттар / жылдағы күндер", "low": None,
                 "base": f"{P['hours_day']} / {P['days_year']}", "high": None, "Өлшем": "сағ / күн",
                 "Дереккөз": cfg["road"]["time_source"]})
    sc = cfg["scenario"]
    for k, name, unit in [("car_occupancy", "Жеңіл көлік толуы", "адам"), ("bus_capacity", "Автобус сыйымдылығы", "адам"),
                          ("bus_occupancy", "Автобустың орташа толуы", "адам")]:
        rows.append({"Параметр": name, "low": sc[k]["low"], "base": sc[k]["base"], "high": sc[k]["high"],
                     "Өлшем": unit, "Дереккөз": sc[k]["source"]})
    eq = cfg["equivalents"]
    for k, name, unit in [("tree_seedling_10y_t_co2", "Қала ағашы (10 жыл)", "т CO2/ағаш"),
                          ("forest_t_co2_per_acre_year", "Орман сіңіруі", "т CO2/акр/жыл"),
                          ("car_t_co2_per_year", "Бензин көлігі", "т CO2e/жыл")]:
        rows.append({"Параметр": name, "low": None, "base": eq[k], "high": None, "Өлшем": unit, "Дереккөз": eq["source"]})
    u = cfg["uncertainty"]
    rows.append({"Параметр": "Монте-Карло: жиындар саны / L ауқымы / әдепкі ε", "low": None,
                 "base": f"{u['mc_runs']} / ±{u['segment_length_rel'] * 100:.0f}% / {u['default_count_error_pct']}%",
                 "high": None, "Өлшем": "", "Дереккөз": u["source"]})
    d = cfg["detection"]
    rows.append({"Параметр": "YOLO моделі / сенімділік / imgsz / кадр қадамы", "low": None,
                 "base": f"{d['model']} / {d['confidence']} / {d['imgsz']} / {d['frame_step']}", "high": None,
                 "Өлшем": "", "Дереккөз": d["source"]})
    return pd.DataFrame(rows)
