"""
reporting.py
------------
Reportes de recursos:
  - por categoría dentro de un escenario;
  - totales por escenario;
  - estadísticas entre escenarios (P5 / P50 / P95 / I90);
  - comparación contra la realidad (IoU, falsos positivos/negativos);
  - comentarios automáticos simples para guiar la discusión.
"""

import numpy as np
import pandas as pd

from classification import CATEGORIES, classify_resources


def block_tonnage(block_size, espesor, densidad):
    """Toneladas de un bloque: área * espesor * densidad.
    Con los valores por defecto: 20*20*20*2.6 = 20 800 t."""
    return block_size * block_size * espesor * densidad


def report_resources_by_category(scenario_name, mask, categories, est,
                                 block_size, espesor, densidad):
    """Tabla de recursos por categoría para un escenario.

    mask       : bloques dentro de la interpretación mineralizada
    categories : categoría por bloque (todos los bloques)
    est        : ley estimada por bloque (Cu%)
    """
    ton_b = block_tonnage(block_size, espesor, densidad)
    area_b = block_size * block_size
    rows = []
    for cat in CATEGORIES + ["Total recurso"]:
        if cat == "Total recurso":
            sel = mask
        else:
            sel = mask & (categories == cat)
        n = int(sel.sum())
        if n == 0:
            rows.append({"Escenario": scenario_name, "Categoría": cat,
                         "N° bloques": 0, "Área m²": 0.0, "Toneladas": 0.0,
                         "Ley media Cu%": np.nan, "Metal Cu (t)": 0.0,
                         "Ley mín": np.nan, "Ley máx": np.nan})
            continue
        # Las leyes pueden tener NaN si el dominio quedó sin muestras
        # (p.ej. un polígono que no encierra ningún sondaje)
        leyes = est[sel]
        finitas = np.isfinite(leyes)
        ton = n * ton_b
        # metal contenido: toneladas * ley(%) / 100, sumado por bloque
        metal = float(np.nansum(ton_b * leyes / 100.0))
        rows.append({
            "Escenario": scenario_name, "Categoría": cat,
            "N° bloques": n,
            "Área m²": n * area_b,
            "Toneladas": ton,
            "Ley media Cu%": (float(np.nanmean(leyes)) if finitas.any()
                              else np.nan),
            "Metal Cu (t)": metal,
            "Ley mín": (float(np.nanmin(leyes)) if finitas.any()
                        else np.nan),
            "Ley máx": (float(np.nanmax(leyes)) if finitas.any()
                        else np.nan),
        })
    return pd.DataFrame(rows)


def report_total_by_scenario(scenarios, dist, d_med, d_ind, d_inf,
                             block_size, espesor, densidad):
    """Tabla resumen con una fila por escenario guardado.

    Cada escenario usa SU PROPIA estimación (sc["est_result"]): la
    estimación cambia entre escenarios porque cambia el dominio.
    Los escenarios sin estimación se omiten.
    """
    ton_b = block_tonnage(block_size, espesor, densidad)
    area_b = block_size * block_size
    rows = []
    for sc in scenarios:
        if sc.get("est_result") is None:
            continue   # aún no estimado
        est = sc["est_result"]["est"]
        mask = sc["mask"]
        n = int(mask.sum())
        cat = classify_resources(dist, mask, d_med, d_ind, d_inf)
        if n == 0:
            rows.append({"Escenario": sc["name"], "Área m²": 0.0,
                         "Toneladas": 0.0, "Ley media Cu%": np.nan,
                         "Metal Cu (t)": 0.0, "% Medido": 0.0,
                         "% Indicado": 0.0, "% Inferido": 0.0,
                         "% No clasificado": 0.0})
            continue
        leyes = est[mask]
        finitas = np.isfinite(leyes)
        metal = float(np.nansum(ton_b * leyes / 100.0))

        def pct(c):
            # porcentaje del tonelaje del escenario en la categoría c
            return 100.0 * (mask & (cat == c)).sum() / n

        rows.append({
            "Escenario": sc["name"],
            "Área m²": n * area_b,
            "Toneladas": n * ton_b,
            "Ley media Cu%": (float(np.nanmean(leyes)) if finitas.any()
                              else np.nan),
            "Metal Cu (t)": metal,
            "% Medido": pct("Medido"),
            "% Indicado": pct("Indicado"),
            "% Inferido": pct("Inferido"),
            "% No clasificado": pct("No clasificado"),
        })
    return pd.DataFrame(rows)


def scenario_percentiles(totals):
    """Estadísticas entre escenarios para toneladas, ley y metal.

    I90_abs = P95 - P5
    I90_rel = 50 * (P95 - P5) / P50   [%]
    """
    rows = []
    variables = [("Toneladas", "Toneladas"),
                 ("Ley Cu %", "Ley media Cu%"),
                 ("Metal Cu t", "Metal Cu (t)")]
    for label, col in variables:
        vals = totals[col].dropna().to_numpy()
        if len(vals) == 0:
            continue
        p5, p50, p95 = np.percentile(vals, [5, 50, 95])
        i90 = p95 - p5
        i90rel = 50.0 * i90 / p50 if p50 > 0 else np.nan
        rows.append({"Variable": label, "P5": p5, "P50": p50, "P95": p95,
                     "I90 abs": i90, "I90 rel %": i90rel})
    return pd.DataFrame(rows)


def compare_with_truth(scenarios, truth_mask, block_size):
    """Métricas de acierto interpretativo de cada escenario vs la realidad,
    calculadas sobre la grilla de bloques.

    IoU = área intersección / área unión (1 = interpretación perfecta).
    """
    area_b = block_size * block_size
    rows = []
    for sc in scenarios:
        m = sc["mask"]
        inter = (m & truth_mask).sum()
        union = (m | truth_mask).sum()
        fp = (m & ~truth_mask).sum()   # interpretado pero estéril real
        fn = (~m & truth_mask).sum()   # mineral real no interpretado
        rows.append({
            "Escenario": sc["name"],
            "Área interpretada m²": m.sum() * area_b,
            "Área verdadera m²": truth_mask.sum() * area_b,
            "Área intersección m²": inter * area_b,
            "Área unión m²": union * area_b,
            "IoU": inter / union if union > 0 else 0.0,
            "Falso positivo m²": fp * area_b,
            "Falso negativo m²": fn * area_b,
        })
    return pd.DataFrame(rows)


def auto_comments(perc, totals, meta=5):
    """Comentarios automáticos simples para guiar la interpretación
    (heurísticas docentes, no juicio experto).

    meta : número objetivo de escenarios que debe dibujar el estudiante.
    """
    out = []
    if perc.empty or len(totals) < 2:
        return ["Guarde al menos 2 escenarios para generar comentarios."]

    def rel(var):
        fila = perc[perc["Variable"] == var]
        return float(fila["I90 rel %"].iloc[0]) if not fila.empty else np.nan

    r_ton, r_ley, r_metal = rel("Toneladas"), rel("Ley Cu %"), rel("Metal Cu t")

    if np.isfinite(r_ton) and np.isfinite(r_ley):
        if r_ton > r_ley * 1.5:
            out.append(f"El tonelaje (I90 rel ≈ {r_ton:.0f}%) es bastante más "
                       f"sensible a la interpretación que la ley media "
                       f"(≈ {r_ley:.0f}%): el contorno del polígono controla "
                       f"el volumen reportado.")
        elif r_ley > r_ton * 1.5:
            out.append(f"La ley media (I90 rel ≈ {r_ley:.0f}%) varía más que "
                       f"el tonelaje (≈ {r_ton:.0f}%): los escenarios "
                       f"incluyen/excluyen zonas de ley muy distinta.")
        else:
            out.append(f"Tonelaje y ley muestran sensibilidad comparable a la "
                       f"interpretación (I90 rel ≈ {r_ton:.0f}% y "
                       f"{r_ley:.0f}%).")
    if np.isfinite(r_metal):
        out.append(f"El metal contenido tiene un I90 relativo ≈ {r_metal:.0f}%: "
                   f"combina el efecto de tonelaje y ley.")

    t = totals.dropna(subset=["Metal Cu (t)"])
    if len(t) >= 2:
        opt = t.loc[t["Metal Cu (t)"].idxmax(), "Escenario"]
        con = t.loc[t["Metal Cu (t)"].idxmin(), "Escenario"]
        out.append(f"Escenario más optimista en metal: {opt}; "
                   f"más conservador: {con}.")
    if len(totals) < meta:
        out.append(f"Lleva {len(totals)} de {meta} escenarios: dibuje más "
                   f"interpretaciones plausibles antes de concluir.")
    return out
