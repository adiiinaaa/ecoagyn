"""Сценарии «автобус вместо машины» (раздел 7).

p — доля поездок на легковых, заменённых автобусом.
Пассажиры, пересевшие в автобус: P = p · N_car · n_car (n_car — заполненность легковой).
Сценарий А: без дополнительных рейсов — существующие автобусы забирают пассажиров,
            из потока просто исчезают p · N_car легковых.
Сценарий Ә: дополнительные автобусы  N_bus+ = ceil(P / C_bus), C_bus — вместимость.
ΔM = M_исх − M_сцен,   r = ΔM / M_исх · 100%.

Точка безубыточности (CO2 на пассажиро-км):
  легковая: e_car = (c_car/100 · k_car) / n_car
  автобус:  e_bus(n) = (c_bus/100 · k_bus) / n
  e_bus(n) < e_car  ⇔  n > n* = (c_bus · k_bus · n_car) / (c_car · k_car)
"""
import math

import numpy as np

from core.analysis import counts_by_class
from core.uncertainty import total


def run_scenario(run, params, p, occ_car, cap_bus, pols, hour=True):
    """Возвращает словарь: исходные, А и Ә для CO2 и каждого загрязнителя (в час)."""
    N = counts_by_class(run)
    h = 3600 / run["summary"]["duration_s"] if hour else 1.0
    Nh = {c: v * h for c, v in N.items()}
    base = {q: total(Nh, params, q) for q in ["CO2", *pols]}
    removed = p * Nh.get("car", 0)
    pax = removed * occ_car
    extra_bus = math.ceil(pax / cap_bus - 1e-9) if pax > 0 else 0
    nA = dict(Nh, car=Nh.get("car", 0) - removed)
    nB = dict(nA, bus=Nh.get("bus", 0) + extra_bus)
    A = {q: total(nA, params, q) for q in base}
    B = {q: total(nB, params, q) for q in base}
    out = {"removed_cars": removed, "passengers": pax, "extra_buses": extra_bus, "rows": []}
    for q in base:
        for name, sc in [("А", A), ("Ә", B)]:
            d = base[q] - sc[q]
            out["rows"].append({"Көрсеткіш": q, "Сценарий": name, "Бастапқы": base[q], "Сценарий мәні": sc[q],
                                "ΔM": d, "r, %": d / base[q] * 100 if base[q] else np.nan})
    return out


def per_passenger(params, occ_car):
    """CO2 на пассажиро-км (кг): легковая и функция для автобуса."""
    car, bus = params["cat"]["car"], params["cat"]["bus"]
    e_car_vkm = car["c"][1] / 100 * params["k"][car["fuel"]][1]     # кг CO2 / машино-км
    e_bus_vkm = bus["c"][1] / 100 * params["k"][bus["fuel"]][1]
    n_star = e_bus_vkm * occ_car / e_car_vkm
    return {"e_car_vkm": e_car_vkm, "e_bus_vkm": e_bus_vkm, "e_car_pkm": e_car_vkm / occ_car, "n_star": n_star}
