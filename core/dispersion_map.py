"""Версия 2 модуля «Ластанудың таралуы»: дорога + котельная на сетке и «дау картасы».

Что считается:
1. Концентрация каждого вещества в каждой клетке сетки = дорога (линейный источник, версия 1)
   + котельная (точечный источник, гауссов факел) + фон.
2. Нормированные концентрации xᵢ = Cᵢ / ПДКᵢ, и два индекса загрязнённости клетки:
   M = max xᵢ («по худшему веществу») и S = Σ xᵢ («по сумме»).
3. Индекс спорности клетки — доля других клеток, с которыми M и S дают ПРОТИВОПОЛОЖНЫЙ
   порядок (по M хуже одна клетка, по S — другая). Ничьи спором не считаются.

Система координат: x — на восток, y — на север, метры, перекрёсток в точке (0, 0).
Направление ветра — метеорологическое: откуда дует (270° — западный ветер, дует на восток).
Все концентрации — в г/м³. Модуль не зависит от Streamlit.
"""
import math

import numpy as np

from core.dispersion import SQRT_2PI, line_concentration, sigma_y_briggs_urban, sigma_z_briggs_urban

MAP_POLLUTANTS = ["NOx", "SO2", "PM2.5", "CO"]
MAP_NORM_KEY = {"NOx": "NO2", "SO2": "SO2", "PM2.5": "PM2.5", "CO": "CO"}


# ---------- Геометрия ----------

def make_grid(half_size_m=500.0, step_m=20.0):
    """Сетка клеток вокруг перекрёстка: X, Y — 2D-массивы координат центров клеток."""
    ax = np.arange(-half_size_m, half_size_m + step_m / 2, step_m)
    return np.meshgrid(ax, ax)


def wind_vector(wind_from_deg):
    """Единичный вектор, КУДА дует ветер (восток, север). Ветер «с 270°» дует на восток."""
    to = math.radians(wind_from_deg + 180.0)
    return math.sin(to), math.cos(to)


def road_vectors(road_azimuth_deg):
    """Направление дороги r и нормаль n к ней (азимут 0° — дорога с юга на север)."""
    a = math.radians(road_azimuth_deg)
    return (math.sin(a), math.cos(a)), (math.cos(a), -math.sin(a))


def wind_road_angle(wind_from_deg, road_azimuth_deg):
    """θ — угол между ветром и дорогой, 0–90° (90° — ветер поперёк дороги)."""
    w = wind_vector(wind_from_deg)
    r, _ = road_vectors(road_azimuth_deg)
    cos_t = abs(w[0] * r[0] + w[1] * r[1])
    return math.degrees(math.acos(min(1.0, cos_t)))


# ---------- Дорога на сетке ----------

def road_field(X, Y, q, u, wind_from_deg, road_azimuth_deg, stability, h, z, sigma_z0, near_min_m=5.0):
    """Вклад дороги [г/м³] в каждой клетке.
    Дорога — бесконечная прямая через (0, 0). Расстояние до неё d = |p·n|.
    С подветренной стороны — формула линейного источника (версия 1), с наветренной — 0.
    Клетки ближе near_min_m к оси дороги считаются как на расстоянии near_min_m."""
    w = wind_vector(wind_from_deg)
    _, n = road_vectors(road_azimuth_deg)
    d_signed = X * n[0] + Y * n[1]
    wn = w[0] * n[0] + w[1] * n[1]                      # куда ветер сносит относительно нормали
    theta = max(wind_road_angle(wind_from_deg, road_azimuth_deg), 1.0)   # θ < 1° — формула вырождается
    d = np.maximum(np.abs(d_signed), near_min_m)
    downwind = (d_signed * wn > 0) | (np.abs(d_signed) < near_min_m)
    c = line_concentration(d, q, u, theta, stability, h, z, sigma_z0)
    return np.where(downwind, c, 0.0)


# ---------- Котельная: точечный источник ----------

def point_source(x_down, y_cross, Q, u, stability, H, z):
    """Гауссов факел точечного источника с отражением от земли (Turner, 1970):
        C = Q / (2π · u · σy · σz) · exp(−y²/(2σy²)) · [exp(−(z−H)²/(2σz²)) + exp(−(z+H)²/(2σz²))]
    x_down — расстояние по ветру от трубы [м], y_cross — поперёк ветра [м], Q [г/с], H — высота трубы.
    Подъём факела не учитывается (эффективная высота = H). Против ветра (x ≤ 0) — 0."""
    x = np.asarray(x_down, dtype=float)
    y = np.asarray(y_cross, dtype=float)
    xs = np.maximum(x, 1.0)                              # чтобы не делить на ноль у самой трубы
    sy = sigma_y_briggs_urban(xs, stability)
    sz = sigma_z_briggs_urban(xs, stability)
    c = Q / (2 * math.pi * u * sy * sz) * np.exp(-y ** 2 / (2 * sy ** 2)) * (
        np.exp(-(z - H) ** 2 / (2 * sz ** 2)) + np.exp(-(z + H) ** 2 / (2 * sz ** 2)))
    return np.where(x > 0, c, 0.0)


def boiler_field(X, Y, Q, u, wind_from_deg, stability, src_x, src_y, H, z):
    """Вклад котельной [г/м³] в каждой клетке: переводим клетку в систему «по ветру / поперёк»."""
    w = wind_vector(wind_from_deg)
    dx, dy = X - src_x, Y - src_y
    x_down = dx * w[0] + dy * w[1]
    y_cross = -dx * w[1] + dy * w[0]
    return point_source(x_down, y_cross, Q, u, stability, H, z)


# ---------- SO2 от дороги (EMEP/EEA) ----------

def road_so2_q(cfg, run, params, sulphur_ppm):
    """q SO2 от дороги [г/(м·с)] по EMEP/EEA: E_SO2 = 2 · k_S · FC (формула (2), Table 3-14).
    2 — отношение молярных масс SO2 и S (64/32): вся сера топлива превращается в SO2.
    FC — масса сожжённого топлива [г] = Σ N_j · L · c_j/100 · ρ, k_S — доля серы [г/г] = ppm·10⁻⁶."""
    from core.analysis import counts_by_class
    N = counts_by_class(run)
    L_km = params["L"]
    e = 0.0
    for cls, n in N.items():
        entry = params["cat"][cls]
        rho_g_per_l = cfg["fuels"][entry["fuel"]]["density_kg_per_l"] * 1000.0
        fc_g = n * L_km * entry["c"][1] / 100.0 * rho_g_per_l      # г топлива за видео
        e += 2.0 * sulphur_ppm.get(entry["fuel"], 0) * 1e-6 * fc_g
    T = run["summary"]["duration_s"]
    return e / (T * L_km * 1000.0)


# ---------- Индексы ----------

def normalized(conc, limits):
    """xᵢ = Cᵢ / ПДКᵢ для веществ, у которых есть ПДК. conc, limits — словари по веществам."""
    return {p: conc[p] / limits[p] for p in conc if limits.get(p)}


def max_sum_index(x):
    """M = max xᵢ, S = Σ xᵢ и номер худшего вещества (по M) в каждой клетке.
    Где загрязнения нет совсем (M = 0), худшего вещества нет: номер −1."""
    names = list(x)
    stack = np.stack([x[p] for p in names])
    M = stack.max(axis=0)
    worst = np.where(M > 0, stack.argmax(axis=0), -1)
    return M, stack.sum(axis=0), worst, names


def dispute_index(M, S, chunk=400):
    """Индекс спорности: для каждой клетки — доля ДРУГИХ клеток j, у которых
    (M_i − M_j)·(S_i − S_j) < 0, т.е. по M хуже одна клетка, а по S — другая.
    Равенства (ничьи) спором не считаются. Возвращает массив той же формы, что M."""
    m, s = np.ravel(M), np.ravel(S)
    n = m.size
    out = np.zeros(n)
    for i in range(0, n, chunk):
        dm = m[i:i + chunk, None] - m[None, :]
        ds = s[i:i + chunk, None] - s[None, :]
        out[i:i + chunk] = (dm * ds < 0).sum(axis=1)
    return (out / max(1, n - 1)).reshape(np.shape(M))


def compute_map(X, Y, q_road, Q_boiler, background, limits, u, wind_from_deg, road_azimuth_deg, stability,
                h, z, sigma_z0, src_x, src_y, H, near_min_m=5.0):
    """Полный расчёт карты. Словари по веществам: q_road [г/(м·с)], Q_boiler [г/с],
    background [г/м³], limits [г/м³]. Возвращает словарь с полями концентраций и индексами."""
    conc = {}
    for p in MAP_POLLUTANTS:
        c = road_field(X, Y, q_road.get(p, 0.0), u, wind_from_deg, road_azimuth_deg, stability, h, z,
                       sigma_z0, near_min_m)
        if Q_boiler.get(p, 0.0) > 0:
            c = c + boiler_field(X, Y, Q_boiler[p], u, wind_from_deg, stability, src_x, src_y, H, z)
        conc[p] = c + background.get(p, 0.0)
    x = normalized(conc, limits)
    M, S, worst, names = max_sum_index(x)
    return {"conc": conc, "x": x, "M": M, "S": S, "worst": worst, "names": names,
            "dispute": dispute_index(M, S), "theta": wind_road_angle(wind_from_deg, road_azimuth_deg)}


def summary_tables(res):
    """Итоги по карте: (по веществам, общие показатели) — списки словарей."""
    n = res["M"].size
    per_pol = [{"Зат": p, "max xᵢ = C/ПДК": float(res["x"][p].max()),
                "Ең нашар клеткалар үлесі, %": float((res["worst"] == k).sum() / n * 100)}
               for k, p in enumerate(res["names"])]
    d = res["dispute"]
    overall = [
        {"Көрсеткіш": "Клеткалар саны", "Мән": n},
        {"Көрсеткіш": "Ластанбаған клеткалар (M = 0), %", "Мән": float((res["worst"] < 0).sum() / n * 100)},
        {"Көрсеткіш": "max M (ең нашар зат бойынша)", "Мән": float(res["M"].max())},
        {"Көрсеткіш": "max S (қосынды бойынша)", "Мән": float(res["S"].max())},
        {"Көрсеткіш": "M > 1 клеткалар (ПДК асқан), %", "Мән": float((res["M"] > 1).sum() / n * 100)},
        {"Көрсеткіш": "Даулылық индексі, орташа", "Мән": float(d.mean())},
        {"Көрсеткіш": "Даулылық индексі, max", "Мән": float(d.max())},
        {"Көрсеткіш": "Даулы клеткалар (индекс > 0), %", "Мән": float((d > 0).sum() / n * 100)},
    ]
    return per_pol, overall
