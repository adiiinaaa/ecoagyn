"""Статистика потока (раздел 6).

По интервалам 30 с: среднее x̄, дисперсия s², индекс дисперсии ID = s² / x̄.
Для пуассоновского (случайного) потока ID ≈ 1. ID > 1 — машины едут «пачками»
(например, из-за светофора), ID < 1 — поток более равномерный.
Критерий хи-квадрат сравнивает гистограмму с распределением Пуассона.
"""
import numpy as np
import pandas as pd
from scipy import stats


def basic(counts):
    x = np.asarray(counts, dtype=float)
    mean = x.mean()
    var = x.var(ddof=1) if len(x) > 1 else 0.0
    return {"n": len(x), "mean": mean, "var": var, "ID": var / mean if mean > 0 else np.nan}


def poisson_test(counts, min_expected=5):
    """Хи-квадрат Пирсона: наблюдаемые частоты vs Пуассон(λ = x̄).
    Соседние значения объединяем, пока ожидаемая частота < min_expected."""
    x = np.asarray(counts, dtype=int)
    n, lam = len(x), x.mean()
    kmax = int(x.max())
    obs = np.array([(x == k).sum() for k in range(kmax + 1)], dtype=float)
    p = stats.poisson.pmf(np.arange(kmax + 1), lam)
    p[-1] += stats.poisson.sf(kmax, lam)          # хвост «≥ kmax» в последнюю ячейку
    exp = n * p
    # Объединение ячеек слева направо
    bins, o_acc, e_acc, lo = [], 0.0, 0.0, 0
    for k in range(kmax + 1):
        o_acc += obs[k]
        e_acc += exp[k]
        if e_acc >= min_expected:
            bins.append((lo, k, o_acc, e_acc))
            o_acc, e_acc, lo = 0.0, 0.0, k + 1
    if e_acc > 0:
        if bins:
            a, _, o, e = bins.pop()
            bins.append((a, kmax, o + o_acc, e + e_acc))
        else:
            bins.append((lo, kmax, o_acc, e_acc))
    O = np.array([b[2] for b in bins])
    E = np.array([b[3] for b in bins])
    chi2 = float(((O - E) ** 2 / E).sum()) if len(bins) else np.nan
    df = len(bins) - 2                              # −1 (сумма) −1 (оценили λ)
    pval = float(stats.chi2.sf(chi2, df)) if df > 0 else np.nan
    table = pd.DataFrame({"Аралық (k)": [f"{a}" if a == b else f"{a}–{b}" for a, b, _, _ in bins],
                          "Бақыланған": O, "Күтілетін (Пуассон)": E.round(2)})
    return {"lambda": lam, "chi2": chi2, "df": df, "p": pval, "obs": obs, "exp": exp, "table": table,
            "chi2_crit": float(stats.chi2.ppf(0.95, df)) if df > 0 else np.nan}


def conclusion_kz(b, t):
    """Вывод на казахском."""
    if np.isnan(t["p"]):
        return ("Хи-квадрат критерийін есептеуге деректер жеткіліксіз (аралықтар саны аз). "
                "Ұзағырақ бейне түсіріңіз.")
    if t["p"] >= 0.05:
        return (f"p = {t['p']:.3f} ≥ 0,05: Пуассон таралуынан айырмашылық статистикалық маңызды емес. "
                f"Ағынды кездейсоқ (пуассондық) деп санауға болады (ID = {b['ID']:.2f}).")
    if b["ID"] > 1:
        return (f"p = {t['p']:.3f} < 0,05 және ID = {b['ID']:.2f} > 1: ағын Пуассоннан өзгеше — көліктер "
                "«топ-топ» болып өтеді (бағдаршам әсері).")
    return (f"p = {t['p']:.3f} < 0,05 және ID = {b['ID']:.2f} < 1: ағын Пуассонға қарағанда біркелкі "
            "(көліктер шамамен тең аралықпен өтеді).")
