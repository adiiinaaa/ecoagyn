"""Раздел 9. «Қалай есептелді?» — формулы, параметры, допущения."""
import streamlit as st

from core.common import save_config
from core.emissions import ASSUMPTIONS_KZ
from core.method import FORMULAS, LIMITATIONS_KZ, params_table
from views.state import cfg, params
from views.ui import formulas, header


def render():
    c = cfg()
    P = params()
    header("Қалай есептелді?", "Барлық формулалар, параметрлер және олардың ресми дереккөздері.", "Әдістеме")

    st.header("Формулалар")
    cols = st.columns(2, gap="large")
    for i, (name, tex) in enumerate(FORMULAS):
        with cols[i % 2]:
            formulas([(name, tex)])
    st.markdown("Белгілер: $N_j$ — $j$ санатындағы көлік саны; $L$ — учаске ұзындығы, км; $c_j$ — отын шығыны, "
                "л/100 км; $k_j$ — 1 л отыннан шығатын CO2, кг; $EF_j$ — шығарынды коэффициенті, г/км; "
                "$\\rho$ — отын тығыздығы; $h_{белс}$ — тәуліктегі белсенді сағаттар; $D$ — жылдағы күн саны.")

    st.header("Барлық параметрлер және дереккөздер")
    st.caption("Ағымдағы мәндер (4-бөлімде өзгертілген болса — өзгертілген түрінде).")
    df = params_table(c, P)
    for col in ("low", "base", "high"):           # в колонках и числа, и текст → показываем как текст
        df[col] = df[col].map(lambda v: "" if v is None or v != v else f"{v:g}" if isinstance(v, float) else str(v))
    st.dataframe(df, hide_index=True, height=520,
                 column_config={"Дереккөз": st.column_config.TextColumn(width="large")})
    st.download_button("Кестені жүктеу (CSV)", df.to_csv(index=False).encode("utf-8-sig"), "parameters.csv")

    st.header("Жорамалдар")
    for a in ASSUMPTIONS_KZ:
        st.markdown(f"- {a}")
    st.header("Шектеулер")
    for a in LIMITATIONS_KZ:
        st.markdown(f"- {a}")

    st.header("Негізгі дереккөздер")
    st.markdown(
        "- EMEP/EEA air pollutant emission inventory guidebook 2023 – Update 2026, 1.A.3.b.i-iv Road transport "
        "(Tables 3-1, 3-5…3-7, 3-12, 3-15, 3-27, 3-28). "
        "[eea.europa.eu](https://www.eea.europa.eu/en/analysis/publications/emep-eea-guidebook-2023)\n"
        "- 2006 IPCC Guidelines for National Greenhouse Gas Inventories, Vol. 2 Energy: Ch. 1 Table 1.2, "
        "Ch. 3 Table 3.2.1; Vol. 1 Ch. 3 Uncertainties. "
        "[ipcc-nggip.iges.or.jp](https://www.ipcc-nggip.iges.or.jp/public/2006gl/vol2.html)\n"
        "- U.S. EPA Greenhouse Gas Equivalencies Calculator — Calculations and References. "
        "[epa.gov](https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator-calculations-and-references)\n"
        "- EEA indicator TERM 029: Occupancy rates of passenger vehicles.\n"
        "- UK Department for Transport, Bus statistics (BUS03).\n"
        "- Ultralytics YOLO11; ByteTrack (Zhang et al., 2022).")

    st.divider()
    st.caption("Параметрлерді (L, сағаттар) config.json-ға әдепкі мән ретінде сақтау:")
    if st.button("L және уақыт параметрлерін config.json-ға сақтау"):
        c["road"]["segment_length_km"] = P["L"]
        c["road"]["active_hours_per_day"] = P["hours_day"]
        c["road"]["days_per_year"] = P["days_year"]
        save_config(c)
        st.success("Сақталды.")
