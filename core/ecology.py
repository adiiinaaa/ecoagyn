"""Экологический итог (раздел 8): ключевые числа, эквиваленты, текст выводов."""
from core.analysis import interval_counts
from core.emissions import compare_models, scale_factors
from core.scenarios import per_passenger, run_scenario


def key_numbers(cfg, run, params):
    pols = cfg["pollutants_main"]
    m1 = compare_models(cfg, run, params, "base", pols)["1"].iloc[-1]
    sf = scale_factors(run, params)
    out = {"veh_h": m1["N"] * sf["hour"], "fuel_h": m1["Q_l"] * sf["hour"]}
    for per in ("hour", "day", "year"):
        out[f"co2_{per}"] = m1["M_kg"] * sf[per]
        for p in pols:
            out[f"{p}_{per}"] = m1[f"{p}_kg"] * sf[per]
    return out


def equivalents(cfg, co2_year_kg):
    """Эквиваленты по U.S. EPA (см. config.equivalents)."""
    e = cfg["equivalents"]
    t = co2_year_kg / 1000
    return {
        "seedlings_10y": t / e["tree_seedling_10y_t_co2"],
        "forest_ha": t / e["forest_t_co2_per_acre_year"] * e["acre_to_ha"],
        "car_years": t / e["car_t_co2_per_year"],
    }


def busiest(run, width=60, top=5):
    s = run["summary"]
    df = interval_counts(run["events"], s["from_s"], s["to_s"], width)
    df = df[df["length_s"] >= width - 0.1]
    return df.sort_values("total", ascending=False).head(top)


def conclusions_kz(cfg, run, params):
    """Автоматический текст выводов и рекомендаций (на казахском)."""
    k = key_numbers(cfg, run, params)
    eq = equivalents(cfg, k["co2_year"])
    sc = cfg["scenario"]
    occ, cap, occ_bus = sc["car_occupancy"]["base"], sc["bus_capacity"]["base"], sc["bus_occupancy"]["base"]
    pols = cfg["pollutants_main"]
    r20 = run_scenario(run, params, 0.20, occ, cap, pols)
    rA = next(x for x in r20["rows"] if x["Көрсеткіш"] == "CO2" and x["Сценарий"] == "А")
    rB = next(x for x in r20["rows"] if x["Көрсеткіш"] == "CO2" and x["Сценарий"] == "Ә")
    pp = per_passenger(params, occ)
    b = busiest(run, 60, 1)
    car_share = None
    s = run["summary"]
    tot = sum(s["counts"][c]["1"] + s["counts"][c]["2"] for c in s["counts"])
    if tot:
        car_share = (s["counts"]["car"]["1"] + s["counts"]["car"]["2"]) / tot * 100
    lines = [
        f"Бақыланған учаскеде (L = {params['L']:g} км) сағатына шамамен {k['veh_h']:.0f} көлік өтеді"
        + (f", оның {car_share:.0f}%-ы — жеңіл көліктер." if car_share is not None else "."),
        f"Есептік бағалау бойынша бұл учаскеде сағатына ≈ {k['fuel_h']:.1f} л отын жағылып, "
        f"≈ {k['co2_hour']:.1f} кг CO2 бөлінеді; тәулігіне ≈ {k['co2_day'] / 1000:.2f} т, "
        f"жылына ≈ {k['co2_year'] / 1000:.0f} т CO2.",
        f"Жылдық CO2 мөлшерін сіңіру үшін ≈ {eq['forest_ha']:.0f} га орман (АҚШ орманының орташа көрсеткіші, EPA) "
        f"керек; бұл ≈ {eq['car_years']:.0f} бензин көлігінің бір жылдық шығарындысына тең.",
        f"Ластаушы заттар (сағатына): CO ≈ {k['CO_hour']:.2f} кг, NOx ≈ {k['NOx_hour']:.3f} кг, "
        f"PM2.5 ≈ {k['PM2.5_hour'] * 1000:.1f} г.",
    ]
    if len(b):
        r = b.iloc[0]
        lines.append(f"Ең жүктелген минут: {int(r['from_s'] // 60)}:{int(r['from_s'] % 60):02d}–"
                     f"{int(r['to_s'] // 60)}:{int(r['to_s'] % 60):02d} ({int(r['total'])} көлік).")
    lines.append(f"Жеңіл көлік сапарларының 20%-ы автобусқа ауысса, CO2 А сценарийінде {rA['r, %']:.1f}%-ға, "
                 f"Ә сценарийінде (қосымша {r20['extra_buses']} автобус/сағ) {rB['r, %']:.1f}%-ға азаяды.")
    rec = [
        f"Автобус бір жолаушыға шаққанда жеңіл көліктен тиімді болуы үшін оның орташа толуы n* ≈ "
        f"{pp['n_star']:.0f} адамнан асуы керек; сондықтан автобус маршруттарының толуын арттыру маңызды "
        f"(жиі, ыңғайлы, жылдам қатынас).",
        "Бағдаршамдағы тоқтап-жүрулер шығарындыны арттырады: «жасыл толқын» мен бағдаршам циклдерін реттеу ұсынылады.",
        "Қорытындыларды нақтылау үшін әр түрлі уақытта (таңғы/кешкі шың, демалыс) кемінде 15–20 минуттық "
        "бейнелер түсіріп, 3-бөлімде дәлдікті тексеру қажет.",
        "Бұл — есептік бағалау; ауа сапасын нақты бағалау үшін PM2.5 / NO2 өлшеу құралдарымен салыстыру керек.",
    ]
    return lines, rec
