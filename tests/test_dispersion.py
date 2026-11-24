"""Автотесты модуля «Ластанудың таралуы» (core/dispersion.py).

Запуск из папки ekoagyn:
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.dispersion import (distance_below, from_display, line_concentration, line_source_strength,  # noqa: E402
                             model_warnings, pasquill_class, sigma_z_briggs_urban, to_display)

X = np.arange(5.0, 500.5, 0.5)
BASE = dict(u=3.0, theta_deg=90.0, stability="D", h=0.5, z=1.5, sigma_z0=1.5)


class TestUnits(unittest.TestCase):
    """1. Перевод единиц."""

    def test_line_source_strength(self):
        # 137,085 г NOx за 699,73 с на 1000 м дороги → 1,959·10⁻⁴ г/(м·с)
        q = line_source_strength(137.085, 699.73, 1000.0)
        self.assertAlmostEqual(q, 137.085 / 699730.0, places=12)
        self.assertAlmostEqual(q, 1.9591e-4, delta=1e-8)

    def test_q_does_not_depend_on_segment_length(self):
        # В EcoAgyn выброс пропорционален длине: E = N·L·EF. Тогда q = E/(T·L) от L не зависит.
        ef_g_per_km, n, T = 0.25, 164, 699.73
        q100 = line_source_strength(n * 0.1 * ef_g_per_km, T, 100.0)
        q1000 = line_source_strength(n * 1.0 * ef_g_per_km, T, 1000.0)
        self.assertAlmostEqual(q100, q1000, places=15)

    def test_display_units(self):
        self.assertAlmostEqual(to_display(1e-6, "NOx"), 1.0)      # 1 мкг/м³
        self.assertAlmostEqual(to_display(1e-6, "PM2.5"), 1.0)    # 1 мкг/м³
        self.assertAlmostEqual(to_display(1e-3, "CO"), 1.0)       # 1 мг/м³
        self.assertAlmostEqual(from_display(to_display(3.7e-5, "CO"), "CO"), 3.7e-5)


class TestShape(unittest.TestCase):
    """2–3. Форма профиля и пропорциональность."""

    def test_decreases_with_distance(self):
        c = line_concentration(X, 1e-4, **BASE)
        self.assertTrue(np.all(np.diff(c) < 0), "C(x) должна убывать с расстоянием")
        for cls in "ABCDEF":
            c = line_concentration(X, 1e-4, 3.0, 90.0, cls)
            self.assertTrue(np.all(np.diff(c) < 0), f"класс {cls}")

    def test_proportional_to_q(self):
        c1 = line_concentration(X, 1e-4, **BASE)
        c3 = line_concentration(X, 3e-4, **BASE)
        np.testing.assert_allclose(c3, 3 * c1, rtol=1e-12)

    def test_inverse_to_u(self):
        # σz по Бриггсу не зависит от u, поэтому C ∝ 1/u
        args = {k: v for k, v in BASE.items() if k != "u"}
        c2 = line_concentration(X, 1e-4, u=2.0, **args)
        c4 = line_concentration(X, 1e-4, u=4.0, **args)
        np.testing.assert_allclose(c2, 2 * c4, rtol=1e-12)

    def test_background_is_added(self):
        c0 = line_concentration(X, 1e-4, **BASE)
        cb = line_concentration(X, 1e-4, background=2e-5, **BASE)
        np.testing.assert_allclose(cb - c0, 2e-5, rtol=1e-9)


class TestHandCalculation(unittest.TestCase):
    """4. Одно значение посчитано вручную."""

    def test_point_x100_class_D(self):
        # q = 1·10⁻⁴ г/(м·с), u = 3 м/с, θ = 90°, класс D, h = 0,5 м, z = 1,5 м, σz0 = 1,5 м, x = 100 м.
        # σz(Бриггс, D) = 0,14·100·(1 + 0,0003·100)^(−0,5) = 14 / √1,03 = 13,7946 м
        # σz итог     = √(1,5² + 13,7946²) = √(2,25 + 190,2913) = 13,8759 м
        # 2σz²         = 385,0825
        # exp(−(1,5−0,5)²/385,0825) = exp(−0,0025968) = 0,997407
        # exp(−(1,5+0,5)²/385,0825) = exp(−0,0103874) = 0,989666   → сумма 1,987073
        # знаменатель  = √(2π)·σz·u = 2,506628·13,8759·3 = 104,3453
        # C = 1·10⁻⁴ / 104,3453 · 1,987073 = 1,9043·10⁻⁶ г/м³ = 1,904 мкг/м³
        c = float(line_concentration(100.0, 1e-4, **BASE))
        self.assertAlmostEqual(c, 1.9043e-6, delta=0.0002e-6)
        self.assertAlmostEqual(float(sigma_z_briggs_urban(100.0, "D")), 13.7946, places=4)


class TestProfileRatio(unittest.TestCase):
    """5. Для одного источника отношение концентраций двух веществ одинаково на любом расстоянии.

    C_i(x) = q_i · f(x), где f(x) — один и тот же «профиль» (метео и геометрия общие).
    Поэтому C_NOx(x) / C_CO(x) = q_NOx / q_CO при любом x: относительный порядок веществ
    нигде не меняется. Это иллюстрирует, что без разных профилей спора нет.
    (Фон должен быть нулевым — фон добавляется, а не умножается.)"""

    def test_ratio_constant(self):
        q_nox, q_co = 1.96e-4, 6.67e-4
        c_nox = line_concentration(X, q_nox, **BASE)
        c_co = line_concentration(X, q_co, **BASE)
        ratio = c_nox / c_co
        np.testing.assert_allclose(ratio, q_nox / q_co, rtol=1e-12)
        self.assertLess(ratio.max() - ratio.min(), 1e-15)

    def test_ratio_constant_for_other_weather(self):
        for cls, theta in [("A", 90.0), ("F", 60.0), ("C", 45.0)]:
            r = line_concentration(X, 2e-4, 2.0, theta, cls) / line_concentration(X, 5e-4, 2.0, theta, cls)
            np.testing.assert_allclose(r, 0.4, rtol=1e-12)


class TestWarnings(unittest.TestCase):
    """6. Предупреждения при u < 1 м/с и θ < 45°."""

    def codes(self, u, th):
        return {code for code, _ in model_warnings(u, th)}

    def test_calm(self):
        self.assertIn("calm", self.codes(0.5, 90))
        self.assertNotIn("calm", self.codes(1.0, 90))

    def test_parallel_wind(self):
        self.assertIn("parallel", self.codes(3, 30))
        self.assertNotIn("parallel", self.codes(3, 45))

    def test_both_and_none(self):
        self.assertEqual(self.codes(0.8, 10), {"calm", "parallel"})
        self.assertEqual(self.codes(3, 90), set())


class TestPasquillAndNorm(unittest.TestCase):
    """Дополнительно: таблица Пасквилла и расстояние до норматива."""

    def test_pasquill_table(self):
        self.assertEqual(pasquill_class(1.5, True, insolation="strong")[0], "A")
        self.assertEqual(pasquill_class(2.5, True, insolation="moderate")[0], "B")
        self.assertEqual(pasquill_class(4.0, True, insolation="moderate")[0], "C")   # B–C → C
        self.assertEqual(pasquill_class(2.5, False, night_cloud="clear")[0], "F")
        self.assertEqual(pasquill_class(4.0, False, night_cloud="cloudy")[0], "D")
        self.assertEqual(pasquill_class(1.5, False, night_cloud="clear")[0], "F")    # пустая ячейка → F
        self.assertEqual(pasquill_class(1.5, True, insolation="strong", overcast=True)[0], "D")

    def test_distance_below(self):
        c = line_concentration(X, 1e-4, **BASE)
        limit = float(line_concentration(100.0, 1e-4, **BASE))
        d, status = distance_below(X, c, limit)
        self.assertEqual(status, "ok")
        self.assertAlmostEqual(d, 100.0, delta=0.5)
        self.assertEqual(distance_below(X, c, None)[1], "no_limit")
        self.assertEqual(distance_below(X, c, 1.0)[1], "already")
        self.assertEqual(distance_below(X, c, 1e-12)[1], "beyond")

    def test_oblique_wind_uses_travel_distance(self):
        # при θ = 30° путь воздуха до точки x = 50 м равен 50 / sin30° = 100 м
        c = float(line_concentration(50.0, 1e-4, 3.0, 30.0, "D"))
        sz = math.sqrt(1.5 ** 2 + float(sigma_z_briggs_urban(100.0, "D")) ** 2)
        expected = 1e-4 / (math.sqrt(2 * math.pi) * sz * 3.0 * 0.5) * (
            math.exp(-1 / (2 * sz ** 2)) + math.exp(-4 / (2 * sz ** 2)))
        self.assertAlmostEqual(c, expected, places=15)


if __name__ == "__main__":
    unittest.main()
