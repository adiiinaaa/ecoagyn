"""Неопределённость (раздел 5): сценарии, торнадо, Монте-Карло, вклад источников.

Считаем по 1-модели (по типам транспорта), результат — в час.
Распределения параметров в Монте-Карло — треугольные (low, base, high),
как рекомендует IPCC 2006, Vol.1 Ch.3 при известных min/most likely/max.
"""
import copy

import numpy as np

from core.analysis import counts_by_class
from core.emissions import calc_entry, category_entry

LEVEL_KZ = {"low": "Төмен (low)", "base": "Негізгі (base)", "high": "Жоғары (high)"}


def count_error(run, cfg):
    """ε — относительная ошибка подсчёта (доля). Из раздела 3, иначе из config."""
    acc = run.get("accuracy") or {}
    if acc.get("eps_total_pct") is not None:
        return abs(acc["eps_total_pct"]) / 100, "3-бөлім (қолмен санау)"
    return cfg["uncertainty"]["default_count_error_pct"] / 100, "config.json (әдепкі мән)"


def corrected_counts(run):
    """N с учётом матрицы ошибок: N_true = Σ_pred N_pred · P(true | pred).
    Если разметки нет — None."""
    acc = run.get("accuracy") or {}
    P = acc.get("p_true_given_pred")
    if not P:
        return None
    N = counts_by_class(run)
    out = {c: 0.0 for c in N}
    for pred, n in N.items():
        row = P.get(pred)
        if not row:
            out[pred] += n
            continue
        for true, p in row.items():
            if true in out:              # «не машина» / «дубль» — просто убираем
                out[true] += n * p
    return out


def total(N, params, pol="CO2", level_over=None, L=None, hour=1.0):
    """Итог (в час) по 1-модели. level_over = {(категория|'*', параметр): уровень}."""
    level_over = level_over or {}
    L = params["L"] if L is None else L
    s = 0.0
    for c, n in N.items():
        e = params["cat"][c]
        lv = lambda what: level_over.get((c, what), level_over.get(("*", what), "base"))  # noqa: E731
        i = {"low": 0, "base": 1, "high": 2}
        cc = e["c"][i[lv("c")]]
        k = params["k"][e["fuel"]][i[lv("k")]]
        if pol == "CO2":
            s = s + n * hour * L * cc / 100 * k
        else:
            s = s + n * hour * L * e["ef"][pol][i[lv("ef")]] / 1000
    return s


def scenarios(run, params, eps, pols):
    """Сценарии low/base/high: все параметры одновременно на низком/высоком уровне."""
    N = counts_by_class(run)
    h = 3600 / run["summary"]["duration_s"]
    out = {}
    for lev, f, Lf in [("low", 1 - eps, 0.9), ("base", 1, 1), ("high", 1 + eps, 1.1)]:
        Nn = {c: v * f for c, v in N.items()}
        ov = {("*", "c"): lev, ("*", "k"): lev, ("*", "ef"): lev}
        out[lev] = {p: total(Nn, params, p, ov, params["L"] * Lf, h) for p in ["CO2", *pols]}
    return out


def tornado(cfg, run, params, eps, pol="CO2"):
    """Меняем по одному фактору, остальные — base. Возвращает список
    (фактор, значение_низ, значение_верх, base)."""
    N = counts_by_class(run)
    h = 3600 / run["summary"]["duration_s"]
    base = total(N, params, pol, hour=h)
    rows = []
    # 1. Число машин ± ε
    rows.append(("Көлік саны ± ε", total({c: v * (1 - eps) for c, v in N.items()}, params, pol, hour=h),
                 total({c: v * (1 + eps) for c, v in N.items()}, params, pol, hour=h)))
    # 2. Доли типов (матрица ошибок из 3-бөлім)
    Nc = corrected_counts(run)
    if Nc:
        v = total(Nc, params, pol, hour=h)
        rows.append(("Түрлер үлесі (қате матрицасы)", min(v, base), max(v, base)))
    # 3. Расход топлива low/high
    rows.append(("Отын шығыны (low/high)", total(N, params, pol, {("*", "c"): "low"}, hour=h),
                 total(N, params, pol, {("*", "c"): "high"}, hour=h)))
    # 4. Вид топлива для легковых: все варианты из config
    vals = []
    for fuel in cfg["categories"]["car"]["fuels"]:
        p2 = copy.deepcopy(params)
        p2["cat"]["car"] = category_entry(cfg, "categories", "car", fuel)
        vals.append(total(N, p2, pol, hour=h))
    rows.append(("Жеңіл көлік отыны (бензин/дизель/газ)", min(vals), max(vals)))
    # 5. Длина участка ±10%
    Lr = cfg["uncertainty"]["segment_length_rel"]
    rows.append((f"Учаске ұзындығы L ± {Lr * 100:.0f}%", total(N, params, pol, L=params["L"] * (1 - Lr), hour=h),
                 total(N, params, pol, L=params["L"] * (1 + Lr), hour=h)))
    # 6. Коэффициенты: k для CO2, EF для загрязнителей
    what = "k" if pol == "CO2" else "ef"
    name = "CO2 коэффициенті k (low/high)" if pol == "CO2" else f"{pol} шығарынды коэффициенті (low/high)"
    rows.append((name, total(N, params, pol, {("*", what): "low"}, hour=h),
                 total(N, params, pol, {("*", what): "high"}, hour=h)))
    rows = [(n, min(a, b), max(a, b), base) for n, a, b in rows]
    rows.sort(key=lambda r: r[2] - r[1])
    return rows


def _tri(rng, lo, mode, hi, n):
    """Треугольное распределение (если lo == hi — константа)."""
    lo, hi = min(lo, mode), max(hi, mode)
    if hi - lo < 1e-12:
        return np.full(n, mode, dtype=float)
    return rng.triangular(lo, mode, hi, n)


def monte_carlo(cfg, run, params, eps, pols, n=None, groups=("recog", "assume"), seed=None):
    """n случайных наборов параметров. groups — какие источники неопределённости
    включены: 'recog' (распознавание: число и доли) и/или 'assume' (допущения:
    расход, k, EF, L). Возвращает словарь массивов (в час)."""
    n = n or cfg["uncertainty"]["mc_runs"]
    rng = np.random.default_rng(cfg["uncertainty"]["mc_seed"] if seed is None else seed)
    N = counts_by_class(run)
    Nc = corrected_counts(run) or N
    h = 3600 / run["summary"]["duration_s"]
    Lr = cfg["uncertainty"]["segment_length_rel"]
    recog, assume = "recog" in groups, "assume" in groups

    mult = _tri(rng, 1 - eps, 1, 1 + eps, n) if recog else np.ones(n)
    w = rng.uniform(0, 1, n) if recog else np.zeros(n)       # смесь «как есть» ↔ «исправлено»
    L = _tri(rng, params["L"] * (1 - Lr), params["L"], params["L"] * (1 + Lr), n) if assume else params["L"]
    out = {p: np.zeros(n) for p in ["CO2", *pols]}
    k_draw = {}
    for f, kv in params["k"].items():
        k_draw[f] = _tri(rng, *kv, n) if assume else kv[1]
    for c in N:
        e = params["cat"][c]
        Nj = (N[c] * (1 - w) + Nc[c] * w) * mult * h
        cc = _tri(rng, *e["c"], n) if assume else e["c"][1]
        out["CO2"] += Nj * L * cc / 100 * k_draw[e["fuel"]]
        for p in pols:
            ef = _tri(rng, *e["ef"][p], n) if assume else e["ef"][p][1]
            out[p] += Nj * L * ef / 1000
    return out


def mc_stats(x):
    return {"Орташа": float(np.mean(x)), "Медиана": float(np.median(x)),
            "P5": float(np.percentile(x, 5)), "P95": float(np.percentile(x, 95)),
            "Стандартты ауытқу": float(np.std(x))}


def variance_shares(cfg, run, params, eps, pols):
    """Вклад источников: дисперсия, когда меняется только распознавание,
    и когда меняются только допущения (расход, k, EF, L). Доли нормируем к 100%."""
    a = monte_carlo(cfg, run, params, eps, pols, groups=("recog",))
    b = monte_carlo(cfg, run, params, eps, pols, groups=("assume",))
    out = {}
    for p in a:
        va, vb = np.var(a[p]), np.var(b[p])
        s = va + vb
        out[p] = (va / s * 100, vb / s * 100) if s > 0 else (0.0, 0.0)
    return out
