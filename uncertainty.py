"""
uncertainty.py
--------------
Incertidumbre geológica derivada de los escenarios interpretativos:
  - p(mineral): fracción de escenarios que incluyen cada bloque;
  - p(1-p): medida simple de incertidumbre (máxima en p = 0.5);
  - comparación con la distancia a sondajes.
"""

import numpy as np
import pandas as pd


def compute_p_mineral(scenarios, n_blocks):
    """Probabilidad de mineralización por bloque:

        p = (n° de escenarios donde el bloque está dentro de la
             interpretación mineralizada) / (n° total de escenarios)
    """
    if not scenarios:
        return np.zeros(n_blocks)
    masks = np.stack([sc["mask"] for sc in scenarios])  # (n_esc, n_blocks)
    return masks.mean(axis=0)


def compute_p_one_minus_p(p):
    """Incertidumbre geológica p(1-p): 0 donde todos los escenarios
    coinciden, máxima (0.25) donde la mitad discrepa."""
    return p * (1.0 - p)


def compare_distance_vs_uncertainty(blocks, dist, p1p):
    """Tabla bloque a bloque para comparar la distancia a sondajes con
    la incertidumbre geológica p(1-p)."""
    return pd.DataFrame({
        "block_id": blocks["block_id"],
        "x": blocks["x"],
        "y": blocks["y"],
        "dist_sondaje_m": dist,
        "p_1_menos_p": p1p,
    })
