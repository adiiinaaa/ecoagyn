"""Распространение загрязнения от дороги (модуль «Ластанудың таралуы»).

Версия 1: дорога как бесконечный линейный источник, гауссова модель.

    C(x) = q / (√(2π) · σz · u · sinθ) · [exp(−(z−h)²/(2σz²)) + exp(−(z+h)²/(2σz²))] + C_фон

Откуда формула: стационарная гауссова модель рассеивания (Pasquill, 1961; Turner, 1970,
«Workbook of Atmospheric Dispersion Estimates», раздел о бесконечном линейном источнике).
Второе слагаемое в скобках — «отражение» от земли: примесь не уходит в грунт, а возвращается
в воздух (мнимый источник на глубине −h).

σz(x) — вертикальное рассеивание, формулы Бриггса для городской местности (Briggs, 1973).
Перемешивание воздуха самими машинами учитываем начальным размером облака σz0:
    σz_итог = √(σz0² + σz(x)²).

Все расчёты — в граммах и метрах (г/м³). В мкг/м³ или мг/м³ переводим только при выводе.
Модуль не зависит от Streamlit: его можно вызывать из тестов и других скриптов.
"""
import math

import numpy as np

SQRT_2PI = math.sqrt(2 * math.pi)

# Вещества EcoAgyn, которые показываем, и единицы вывода.
# NOx в EcoAgyn посчитан «в пересчёте на NO2» (EMEP/EEA Guidebook, Table 3-1), поэтому его сравнивают
# с нормативом NO2 — это оценка с запасом (часть NOx в воздухе — NO, а не NO2).
POLLUTANTS = ["NOx", "CO", "PM2.5"]
DISPLAY_UNIT = {"NOx": "мкг/м³", "CO": "мг/м³", "PM2.5": "мкг/м³"}
TO_DISPLAY = {"мкг/м³": 1e6, "мг/м³": 1e3}          # г/м³ → единица вывода
NORM_KEY = {"NOx": "NO2", "CO": "CO", "PM2.5": "PM2.5"}  # с каким нормативом сравниваем


def to_display(c_g_m3, pollutant):
    """г/м³ → мкг/м³ (NOx, PM2.5) или мг/м³ (CO)."""
    return c_g_m3 * TO_DISPLAY[DISPLAY_UNIT[pollutant]]


def from_display(value, pollutant):
    """Обратный перевод: мкг/м³ или мг/м³ → г/м³."""
    return value / TO_DISPLAY[DISPLAY_UNIT[pollutant]]


# ---------- Мощность линейного источника ----------

def line_source_strength(emission_g, duration_s, length_m):
    """q [г/(м·с)] = суммарный выброс [г] / (длительность наблюдения [с] × длина участка [м])."""
    return emission_g / (duration_s * length_m)


def q_from_ecoagyn(cfg, run, params, pollutants=POLLUTANTS):
    """q по каждому веществу из выбросов EcoAgyn (1-модель, по типам транспорта).

    EcoAgyn считает выброс за всё видео на участке длиной L км: E = Σ N_j · L · EF_j.
    Поэтому q = E / (T · L) от L не зависит — это выброс одного метра дороги в секунду.
    Возвращает словарь: вещество → {"E_g", "T_s", "L_m", "q"}."""
    from core.emissions import compare_models
    tot = compare_models(cfg, run, params, "base", pollutants)["1"].iloc[-1]
    T = run["summary"]["duration_s"]
    L_m = params["L"] * 1000.0
    out = {}
    for p in pollutants:
        E_g = float(tot[f"{p}_kg"]) * 1000.0
        out[p] = {"E_g": E_g, "T_s": T, "L_m": L_m, "q": line_source_strength(E_g, T, L_m)}
    return out


# ---------- σz по Бриггсу (город) ----------

def sigma_z_briggs_urban(x, stability):
    """σz(x) [м], Briggs (1973), городская местность; x — расстояние по ветру [м].
    A–B: 0.24·x·(1+0.001x)^0.5;  C: 0.20·x;  D: 0.14·x·(1+0.0003x)^−0.5;  E–F: 0.08·x·(1+0.0015x)^−0.5."""
    x = np.asarray(x, dtype=float)
    s = stability.upper()
    if s in ("A", "B"):
        return 0.24 * x * np.sqrt(1 + 0.001 * x)
    if s == "C":
        return 0.20 * x
    if s == "D":
        return 0.14 * x / np.sqrt(1 + 0.0003 * x)
    if s in ("E", "F"):
        return 0.08 * x / np.sqrt(1 + 0.0015 * x)
    raise ValueError(f"Белгісіз тұрақтылық класы: {stability}")


def sigma_y_briggs_urban(x, stability):
    """σy(x) [м], Briggs (1973), город (нужно для точечного источника, версия 2).
    A–B: 0.32x(1+0.0004x)^−0.5;  C: 0.22x(…);  D: 0.16x(…);  E–F: 0.11x(…)."""
    x = np.asarray(x, dtype=float)
    k = {"A": 0.32, "B": 0.32, "C": 0.22, "D": 0.16, "E": 0.11, "F": 0.11}[stability.upper()]
    return k * x / np.sqrt(1 + 0.0004 * x)


def sigma_z_total(x, stability, sigma_z0):
    """σz с начальным рассеиванием от машин: √(σz0² + σz(x)²)."""
    return np.sqrt(sigma_z0 ** 2 + sigma_z_briggs_urban(x, stability) ** 2)


# ---------- Концентрация ----------

def line_concentration(x, q, u, theta_deg, stability, h=0.5, z=1.5, sigma_z0=1.5, background=0.0):
    """C(x) [г/м³] от бесконечного линейного источника.

    x         — расстояние от дороги [м] (перпендикулярно дороге), число или массив;
    q         — мощность источника [г/(м·с)];
    u         — скорость ветра на высоте 10 м [м/с];
    theta_deg — угол между ветром и дорогой [°], 90° — ветер поперёк дороги;
    h, z      — высота выброса и высота точки наблюдения [м];
    sigma_z0  — начальное вертикальное рассеивание от машин [м];
    background— фоновая концентрация [г/м³].

    При косом ветре воздух от дороги до точки на расстоянии x проходит путь x / sinθ,
    поэтому σz берём на этом пути (Turner, 1970). При θ = 90° это просто σz(x)."""
    s = math.sin(math.radians(theta_deg))
    sz = sigma_z_total(np.asarray(x, dtype=float) / s, stability, sigma_z0)
    vertical = np.exp(-(z - h) ** 2 / (2 * sz ** 2)) + np.exp(-(z + h) ** 2 / (2 * sz ** 2))
    return q / (SQRT_2PI * sz * u * s) * vertical + background


def distance_below(x, c, limit):
    """Расстояние [м], начиная с которого концентрация ВСЕГДА ниже норматива.
    Возвращает (значение, статус): статус 'ok', 'already' (ниже уже у дороги),
    'beyond' (выше норматива на всём графике), 'no_limit' (норматив не задан)."""
    if limit is None or limit <= 0:
        return None, "no_limit"
    x, c = np.asarray(x, float), np.asarray(c, float)
    above = np.where(c > limit)[0]
    if len(above) == 0:
        return float(x[0]), "already"
    i = above[-1]
    if i == len(x) - 1:
        return None, "beyond"
    # линейная интерполяция между последней точкой выше и первой ниже
    x0, x1, c0, c1 = x[i], x[i + 1], c[i], c[i + 1]
    return float(x0 + (c0 - limit) * (x1 - x0) / (c0 - c1)), "ok"


# ---------- Предупреждения ----------

def model_warnings(u, theta_deg):
    """Условия, при которых модель линейного источника неприменима или неточна.
    Возвращает список (код, текст на казахском)."""
    w = []
    if u < 1.0:
        w.append(("calm", "Желдің жылдамдығы 1 м/с-тен аз: тымық кезде модель қолданылмайды "
                          "(формулада u бөлгіште тұр, концентрация шексіз өседі)."))
    if theta_deg < 45:
        w.append(("parallel", "θ < 45°: жел жол бойымен соққанда сызықтық көз моделі дәл емес."))
    return w


# ---------- Классы устойчивости Пасквилла ----------

# Turner (1970), Table 1: «Key to stability categories».
# Скорость ветра на 10 м: <2, 2–3, 3–5, 5–6, >6 м/с.
# День: сильная / умеренная / слабая солнечная радиация.
# Ночь: облачность ≥4/8 / ≤3/8. При сплошной облачности днём и ночью — D.
_DAY = [("A", "A-B", "B"), ("A-B", "B", "C"), ("B", "B-C", "C"), ("C", "C-D", "D"), ("C", "D", "D")]
_NIGHT = [(None, None), ("E", "F"), ("D", "E"), ("D", "D"), ("D", "D")]
INSOLATION = ["strong", "moderate", "slight"]
NIGHT_CLOUD = ["cloudy", "clear"]      # ≥4/8 облаков / ≤3/8


def _u_row(u):
    if u < 2:
        return 0
    if u < 3:
        return 1
    if u < 5:
        return 2
    if u < 6:
        return 3
    return 4


def pasquill_class(u, is_day, insolation="moderate", night_cloud="clear", overcast=False):
    """Класс устойчивости по таблице Пасквилла–Тёрнера.
    Возвращает (класс для расчёта, запись таблицы, пояснение).
    Промежуточные классы (A-B, B-C, C-D) заменяем более устойчивым (B, C, D) —
    он даёт бо́льшую концентрацию, т.е. оценку с запасом. Ночью при u < 2 м/с ячейка
    таблицы пустая — берём F (тоже с запасом)."""
    if overcast:
        return "D", "D", "Тұтас бұлтты — D"
    r = _u_row(u)
    raw = _DAY[r][INSOLATION.index(insolation)] if is_day else _NIGHT[r][NIGHT_CLOUD.index(night_cloud)]
    if raw is None:
        return "F", "—", "Түнде u < 2 м/с: кестеде мән жоқ, F алынды (қор есебімен)"
    cls = raw.split("-")[-1]
    note = f"Кестеде {raw}" + (f", есепке {cls} алынды (тұрақтырақ класс)" if "-" in raw else "")
    return cls, raw, note
