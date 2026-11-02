"""Топливо, CO2 и загрязнители (раздел 4).

Формулы для категории j:
  S_j = N_j · L                    — пробег, км
  Q_j = N_j · L · c_j / 100        — топливо, л          (c_j — л/100 км)
  M_j = Q_j · k_j                  — CO2, кг              (k_j — кг CO2 / л)
  E_j = N_j · L · EF_j             — загрязнитель, г      (EF_j — г/км)
Итог: M = Σ M_j, E = Σ E_j.

Все функции работают и с числами, и с массивами numpy (нужно для Монте-Карло).
"""
import numpy as np
import pandas as pd

LEVELS = ("low", "base", "high")
LI = {"low": 0, "base": 1, "high": 2}


# ---------- Значения по умолчанию из config.json ----------

def fuel_k(cfg, fuel):
    """k — кг CO2 на 1 литр: [low, base, high].
    base = (кг CO2 / кг топлива, EMEP/EEA Table 3-12) × плотность (Table 3-28);
    low/high = IPCC 2006 EF (кг/ТДж) × NCV (ТДж/Гг) / 10^6 × плотность."""
    f = cfg["fuels"][fuel]
    rho = f["density_kg_per_l"]
    ipcc = f["ipcc_ef_kg_per_tj"]
    low = ipcc["low"] * f["ipcc_ncv_tj_per_gg"] / 1e6 * rho
    high = ipcc["high"] * f["ipcc_ncv_tj_per_gg"] / 1e6 * rho
    return [round(low, 3), round(f["co2_kg_per_kg"] * rho, 3), round(high, 3)]


def fc_to_l100(cfg, fuel, g_per_km):
    """г/км → л/100 км через плотность топлива."""
    return g_per_km / (cfg["fuels"][fuel]["density_kg_per_l"] * 1000) * 100


def pollutants(cfg):
    return cfg["pollutants_main"] + cfg["pollutants_extra"]


def entry_defaults(cfg, fuel_entry, fuel):
    """Параметры одной категории для выбранного топлива:
    c (л/100 км) [low, base, high] и EF (г/км) [low, base, high] по каждому загрязнителю.
    EF г/км = EF г/кг топлива (Tier 1) × расход г/км (base) / 1000."""
    fc = fuel_entry["fc_g_per_km"]
    ef_table = cfg["tier1_ef_g_per_kg_fuel"][fuel_entry["tier1"]][fuel]
    ef = {}
    for p in pollutants(cfg):
        if p in ef_table:
            mean, mn, mx = ef_table[p]
            ef[p] = [round(v * fc[1] / 1000, 5) for v in (mn, mean, mx)]
        else:
            ef[p] = [0.0, 0.0, 0.0]      # в источнике нет — не считаем
    return {"fuel": fuel, "tier1": fuel_entry["tier1"],
            "c": [round(fc_to_l100(cfg, fuel, v), 2) for v in fc], "ef": ef,
            "why": fuel_entry.get("why", "")}


def category_entry(cfg, section, key, fuel=None):
    """Параметры категории транспорта для выбранного топлива."""
    cat = cfg[section][key]
    fuel = fuel if fuel in cat["fuels"] else cat["default_fuel"]
    return entry_defaults(cfg, cat["fuels"][fuel], fuel)


def default_params(cfg):
    """Полный набор параметров по умолчанию (дальше их меняют в интерфейсе)."""
    p = {
        "L": cfg["road"]["segment_length_km"],
        "hours_day": cfg["road"]["active_hours_per_day"],
        "days_year": cfg["road"]["days_per_year"],
        "k": {f: fuel_k(cfg, f) for f in cfg["fuels"] if not f.startswith("_")},
        "cat": {c: category_entry(cfg, "categories", c) for c in cfg["classes"]},
    }
    m0 = cfg["model0"]
    p["m0"] = entry_defaults(cfg, m0, m0["fuel"])
    return p


# ---------- Расчёт ----------

def calc_entry(N, L, e, k, level="base", pols=None):
    """Расчёт для одной категории. N может быть массивом (Монте-Карло).
    e — параметры категории, k — [low, base, high] для её топлива."""
    i = LI[level]
    c = e["c"][i] if isinstance(e["c"], list) else e["c"]
    kk = k[i] if isinstance(k, list) else k
    S = N * L
    Q = S * c / 100
    M = Q * kk
    out = {"N": N, "S_km": S, "Q_l": Q, "M_kg": M}
    for p in (pols or e["ef"]):
        ef = e["ef"][p][i] if isinstance(e["ef"][p], list) else e["ef"][p]
        out[f"{p}_kg"] = S * ef / 1000          # граммы → кг
    return out


def calc_model(N_by_key, entries, params, level="base", pols=None):
    """Таблица по категориям + строка «Барлығы» (итог)."""
    rows = []
    for key, N in N_by_key.items():
        if key not in entries:
            continue
        e = entries[key]
        r = calc_entry(N, params["L"], e, params["k"][e["fuel"]], level, pols)
        r["key"] = key
        r["fuel"] = e["fuel"]
        rows.append(r)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    tot = df.drop(columns=["key", "fuel"]).sum(numeric_only=True)
    tot["key"], tot["fuel"] = "total", ""
    return pd.concat([df, pd.DataFrame([tot])], ignore_index=True)


def compare_models(cfg, run, params, level="base", pols=None, counts=None):
    """Две модели: 0 — все машины как одна средняя легковая, 1 — по типам транспорта.
    counts — (необязательно) свои N по классам (для неопределённости)."""
    from core.analysis import counts_by_class
    N = counts or counts_by_class(run)
    m0 = calc_model({"all": sum(N.values())}, {"all": params["m0"]}, params, level, pols)
    m1 = calc_model(N, params["cat"], params, level, pols)
    return {"0": m0, "1": m1}


def scale_factors(run, params):
    """Множители: за видео → в час → в сутки → в год (оценка)."""
    h = 3600 / run["summary"]["duration_s"]
    return {"video": 1.0, "hour": h, "day": h * params["hours_day"],
            "year": h * params["hours_day"] * params["days_year"]}


ASSUMPTIONS_KZ = [
    "Әр көлік учаскенің бүкіл ұзындығын (L) жүріп өтеді деп есептеледі.",
    "Отын түрі көлік санаты бойынша беріледі (бейнеден отын түрін анықтау мүмкін емес).",
    "CO2 тек отынның жануынан есептеледі (майлау майы, өндіріс, отын тасымалы есепке алынбайды).",
    "Бұл — есептеу (бағалау), ауадағы концентрацияны тікелей өлшеу емес.",
    "Отын шығыны мен коэффициенттер — орташа мәндер: жылдамдық, кептеліс, ауа райы, көліктің жасы ескерілмейді.",
    "Сағаттық/тәуліктік/жылдық мәндер бейне ұзақтығынан пропорционалды есептелген (есептік бағалау).",
]
