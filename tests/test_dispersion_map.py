"""Автотесты версии 2 «Ластанудың таралуы»: котельная, сетка, индексы M, S и индекс спорности.

Запуск из папки ekoagyn:
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.dispersion_map import (boiler_field, compute_map, dispute_index, make_grid, max_sum_index,  # noqa: E402
                                 point_source, wind_road_angle)

# ПДК (максимальные разовые, г/м³) — как в norms.json
LIMITS = {"NOx": 0.2e-3, "SO2": 0.5e-3, "PM2.5": 0.16e-3, "CO": 5.0e-3}
# Мощности дороги [г/(м·с)] — порядок величин как у kokshetau_01
Q_ROAD = {"NOx": 1.96e-4, "SO2": 1.6e-7, "PM2.5": 3.3e-6, "CO": 6.67e-4}
Q_BOILER = {"NOx": 1.0, "SO2": 2.0, "PM2.5": 0.2, "CO": 1.0}
MET = dict(u=3.0, wind_from_deg=270.0, road_azimuth_deg=0.0, stability="D", h=0.5, z=1.5, sigma_z0=1.5,
           src_x=300.0, src_y=200.0, H=30.0)


def run_map(Q_boiler, background=None, **over):
    X, Y = make_grid(500, 20)
    kw = dict(MET)
    kw.update(over)
    return compute_map(X, Y, Q_ROAD, Q_boiler, background or {}, LIMITS, **kw)


class TestOneSourceNoDispute(unittest.TestCase):
    """Котельная выключена (Q = 0) → один источник → индекс спорности 0 во всех клетках.

    Почему: при одном источнике Cᵢ = qᵢ·f(клетка) + фонᵢ, где f — общий для всех веществ
    «профиль» (геометрия и метеорология одни и те же). Тогда xᵢ = aᵢ·f + bᵢ, и M = max xᵢ,
    S = Σ xᵢ — обе неубывающие функции одного числа f. Две клетки они всегда упорядочивают
    одинаково (или дают ничью), поэтому противоположного порядка, т.е. спора, нет."""

    def test_q0_no_background(self):
        res = run_map({p: 0.0 for p in Q_BOILER})
        self.assertEqual(float(res["dispute"].max()), 0.0)

    def test_q0_with_background(self):
        bg = {"NOx": 30e-6, "SO2": 15e-6, "PM2.5": 12e-6, "CO": 0.6e-3}
        res = run_map({p: 0.0 for p in Q_BOILER}, background=bg)
        self.assertEqual(float(res["dispute"].max()), 0.0)

    def test_q0_other_weather(self):
        for stab, wind in [("A", 300.0), ("F", 240.0), ("C", 200.0)]:
            res = run_map({p: 0.0 for p in Q_BOILER}, background={"NOx": 20e-6}, stability=stab, wind_from_deg=wind)
            self.assertEqual(float(res["dispute"].max()), 0.0, f"{stab}, {wind}")

    def test_two_sources_can_dispute(self):
        # для контраста: у котельной другой профиль веществ — спор появляется
        res = run_map(Q_BOILER)
        self.assertGreater(float(res["dispute"].max()), 0.0)


class TestPointSource(unittest.TestCase):
    """Гауссов факел котельной."""

    def test_zero_upwind(self):
        c = point_source(np.array([-50.0, -1.0, 0.0]), np.zeros(3), 1.0, 3.0, "D", 30.0, 1.5)
        np.testing.assert_array_equal(c, 0.0)

    def test_symmetric_across_wind(self):
        y = np.array([-80.0, -30.0, 0.0, 30.0, 80.0])
        c = point_source(np.full(5, 400.0), y, 1.0, 3.0, "D", 30.0, 1.5)
        np.testing.assert_allclose(c, c[::-1], rtol=1e-12)
        self.assertEqual(int(np.argmax(c)), 2)        # максимум на оси факела

    def test_proportional_to_Q(self):
        x, y = np.array([200.0, 600.0]), np.array([10.0, -40.0])
        np.testing.assert_allclose(point_source(x, y, 3.0, 3.0, "C", 30.0, 1.5),
                                   3 * point_source(x, y, 1.0, 3.0, "C", 30.0, 1.5), rtol=1e-12)

    def test_hand_value(self):
        # Q = 1 г/с, u = 3 м/с, класс D, H = 30 м, z = 1,5 м, x = 1000 м, y = 0.
        # σy = 0,16·1000·(1+0,4)^−0,5 = 135,225 м;  σz = 0,14·1000·(1+0,3)^−0,5 = 122,788 м
        # скобка = exp(−28,5²/(2·122,788²)) + exp(−31,5²/(2·122,788²)) = 0,973423 + 0,967629 = 1,941052
        # знаменатель = 2π·3·135,225·122,788 = 312 977,7
        # C = 1,941052 / 312 977,7 = 6,2019·10⁻⁶ г/м³
        sy = 0.16 * 1000 / math.sqrt(1.4)
        sz = 0.14 * 1000 / math.sqrt(1.3)
        br = math.exp(-28.5 ** 2 / (2 * sz ** 2)) + math.exp(-31.5 ** 2 / (2 * sz ** 2))
        expected = 1 / (2 * math.pi * 3 * sy * sz) * br
        c = float(point_source(1000.0, 0.0, 1.0, 3.0, "D", 30.0, 1.5))
        self.assertAlmostEqual(c, expected, places=15)
        self.assertAlmostEqual(c, 6.2019e-6, delta=0.0001e-6)

    def test_boiler_field_downwind(self):
        # западный ветер (270°) дует на восток: к востоку от трубы есть загрязнение, к западу — нет
        X, Y = make_grid(500, 20)
        c = boiler_field(X, Y, 1.0, 3.0, 270.0, "D", 0.0, 0.0, 30.0, 1.5)
        self.assertGreater(c[25, 45], 0.0)           # x = +400, y = 0
        self.assertEqual(c[25, 5], 0.0)             # x = −400, y = 0


class TestIndices(unittest.TestCase):
    """M, S, худшее вещество и индекс спорности на маленьких примерах."""

    def test_dispute_by_hand(self):
        # 4 клетки:        A      B      C      D
        M = np.array([0.5, 0.4, 0.6, 0.4])
        S = np.array([0.6, 0.9, 1.0, 0.5])
        # Пары с противоположным порядком: A–B (M: A>B, S: A<B) и B–C? (M: B<C, S: B<C) — нет.
        # A–C: M A<C, S A<C — нет; A–D: M A>D, S A>D — нет; B–D: M ничья — не спор;
        # C–D: M C>D, S C>D — нет.  Итого спорит только пара A–B.
        # Индекс = (число спорных пар клетки) / (n − 1) = 1/3 для A и B, 0 для C и D.
        d = dispute_index(M, S)
        np.testing.assert_allclose(d, [1 / 3, 1 / 3, 0.0, 0.0])

    def test_max_sum_and_worst(self):
        x = {"NOx": np.array([0.3, 0.0, 0.1]), "SO2": np.array([0.5, 0.0, 0.05]), "CO": np.array([0.1, 0.0, 0.0])}
        M, S, worst, names = max_sum_index(x)
        np.testing.assert_allclose(M, [0.5, 0.0, 0.1])
        np.testing.assert_allclose(S, [0.9, 0.0, 0.15])
        self.assertEqual([names[i] if i >= 0 else None for i in worst], ["SO2", None, "NOx"])

    def test_wind_road_angle(self):
        self.assertAlmostEqual(wind_road_angle(270, 0), 90.0)   # западный ветер, дорога С–Ю
        self.assertAlmostEqual(wind_road_angle(180, 0), 0.0)    # южный ветер вдоль дороги
        self.assertAlmostEqual(wind_road_angle(225, 0), 45.0)


if __name__ == "__main__":
    unittest.main()
