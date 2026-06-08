# app.py
# PoPs-Simulator: Probabilidad de superar puntaje de corte (universidad)
# Cambio solicitado (FIXED SCALE):
# - Quitar inputs min/max y fijar escala global X = [450, 1000] para TODOS los gráficos (pruebas y carreras)
# - También clamp de puntajes simulados a [450, 1000] (consistencia visual)
#
# Incluye:
# - Pruebas: M1, M2, Lenguaje, Ciencias, Historia (+ NEM y Ranking fijos)
# - Distribuciones: Normal / Lognormal / Gamma / None (no rendida)
# - Si una prueba está en "None (no rendida)": NO se simula, NO se grafica, y su ponderación efectiva se fuerza a 0
# - Histogramas por prueba + histogramas por carrera (barras rojas sobre el corte)
# - Tabla resultados estilizada (Corte rojo, Prob azul bold) + ranking de probabilidad
# - Avatar circular arriba-izquierda (archivo local "avatar.png")
#
# Requiere: streamlit, numpy, pandas, matplotlib
# Ejecutar: streamlit run app.py

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import base64
from pathlib import Path

st.set_page_config(page_title="PoPs-Simulator", layout="wide")

# -----------------------------
# Global fixed scale (NO UI)
# -----------------------------
X_MIN = 450.0
X_MAX = 1000.0
HIST_BINS = 35


# -----------------------------
# Avatar header (top-left)
# -----------------------------
def img_to_base64(path: str) -> str:
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode("utf-8")


def render_avatar_top_left(img_path: str, size_px: int = 64):
    try:
        b64 = img_to_base64(img_path)
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; gap:14px; margin-bottom: 6px;">
              <img
                src="data:image/png;base64,{b64}"
                style="
                  width:{size_px}px; height:{size_px}px;
                  border-radius:50%;
                  object-fit:cover;
                  border: 2px solid rgba(255,255,255,0.15);
                  box-shadow: 0 2px 10px rgba(0,0,0,0.25);
                "
              />
              <div>
                <div style="font-size: 34px; font-weight: 700; line-height: 1.1;">PoPs-Simulator</div>
                <div style="opacity: 0.85; margin-top: 2px;">
                  Simulación Monte Carlo de puntaje ponderado y probabilidad de superar cortes por carrera.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        st.title("PoPs-Simulator")
        st.caption(
            "Simulación Monte Carlo de puntaje ponderado y probabilidad de superar cortes por carrera. "
            "(Tip: coloca 'avatar.png' junto a app.py para mostrar el avatar circular.)"
        )


# -----------------------------
# Helpers
# -----------------------------
def clamp_scores(x: np.ndarray, lo: float = X_MIN, hi: float = X_MAX) -> np.ndarray:
    return np.clip(x, lo, hi)


def simulate_dist(dist_name: str, n: int, params: dict, seed: int | None = None) -> np.ndarray | None:
    if dist_name == "None (no rendida)":
        return None

    rng = np.random.default_rng(seed)

    if dist_name == "Normal":
        mu = float(params.get("mu", 600.0))
        sigma = float(params.get("sigma", 60.0))
        x = rng.normal(loc=mu, scale=max(sigma, 1e-9), size=n)

    elif dist_name == "Lognormal (mu, sigma)":
        mu_ln = float(params.get("mu_ln", 6.4))
        sigma_ln = float(params.get("sigma_ln", 0.15))
        x = rng.lognormal(mean=mu_ln, sigma=max(sigma_ln, 1e-9), size=n)

    elif dist_name == "Gamma (k, theta)":
        k = float(params.get("k", 12.0))
        theta = float(params.get("theta", 40.0))
        x = rng.gamma(shape=max(k, 1e-9), scale=max(theta, 1e-9), size=n)

    else:
        raise ValueError(f"Distribución no soportada: {dist_name}")

    return x


def plot_hist_with_cut(scores: np.ndarray, cut: float, bins: int = HIST_BINS, title: str = ""):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    counts, edges = np.histogram(scores, bins=bins)
    centres = 0.5 * (edges[:-1] + edges[1:])
    widths = edges[1:] - edges[:-1]

    colours = ["red" if c >= cut else "gray" for c in centres]
    ax.bar(
        centres,
        counts,
        width=widths,
        align="center",
        color=colours,
        edgecolor="white",
        linewidth=0.4,
    )
    ax.axvline(cut, linewidth=2)
    ax.set_title(title)
    ax.set_xlabel("Puntaje ponderado simulado")
    ax.set_ylabel("Frecuencia")
    ax.set_xlim(X_MIN, X_MAX)
    return fig


def plot_hist_basic(x: np.ndarray, bins: int = HIST_BINS, title: str = ""):
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.hist(x, bins=bins, edgecolor="white", linewidth=0.4)
    ax.set_title(title)
    ax.set_xlabel("Puntaje simulado")
    ax.set_ylabel("Frecuencia")
    ax.set_xlim(X_MIN, X_MAX)
    return fig


def nz_array(x: np.ndarray | None, n: int) -> np.ndarray:
    if x is None:
        return np.zeros(n, dtype=float)
    return x


def plot_prob_bar(res_df: pd.DataFrame, title: str = "Probabilidad de superar corte por opción (ordenado)"):
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = res_df["Carrera"].astype(str).tolist()
    y = res_df["Prob(supera corte)"].astype(float).tolist()
    ax.bar(x, y)
    ax.set_title(title)
    ax.set_xlabel("Opción / Carrera")
    ax.set_ylabel("Probabilidad")
    ax.set_ylim(0, 1)
    ax.tick_params(axis="x", rotation=90)
    return fig


def style_results_table(df: pd.DataFrame):
    def highlight_col(col: pd.Series):
        if col.name == "Corte":
            return ["background-color: #b71c1c; color: white; font-weight: 700;" for _ in col]
        if col.name == "Prob(supera corte)":
            return ["background-color: #0d47a1; color: white; font-weight: 800;" for _ in col]
        return ["" for _ in col]

    styler = (
        df.style
        .apply(highlight_col, axis=0)
        .format({
            "Prob(supera corte)": "{:.4f}",
            "P5": "{:.2f}",
            "P50": "{:.2f}",
            "P95": "{:.2f}",
            "E[puntaje]": "{:.2f}",
            "Std[puntaje]": "{:.2f}",
            "Suma ponderaciones (efectiva)": "{:.1f}",
            "Corte": "{:.0f}",
        })
    )
    return styler


# -----------------------------
# Header
# -----------------------------
render_avatar_top_left("avatar.png", size_px=64)

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.header("Inputs base")
    nem = st.number_input("NEM (puntaje)", min_value=100.0, max_value=1000.0, value=734.0, step=1.0)
    ranking = st.number_input("Ranking (puntaje)", min_value=100.0, max_value=1000.0, value=731.0, step=1.0)

    st.divider()
    st.subheader("Monte Carlo")
    n_sims = st.number_input("N realizaciones (N)", min_value=100, max_value=2_000_000, value=50_000, step=1000)
    seed = st.number_input("Semilla (seed)", min_value=0, max_value=10_000_000, value=12345, step=1)

    st.divider()
    st.caption(f"Escala fija para todos los gráficos: X = [{int(X_MIN)}, {int(X_MAX)}]")


# -----------------------------
# Distributions
# -----------------------------
st.subheader("1) Distribuciones a simular (M1, M2, Lenguaje, Ciencias, Historia)")
st.write(
    "Selecciona distribución y parámetros para cada prueba. Se simulan **independientes**. "
    "Si eliges **None (no rendida)**, esa prueba no se simula ni participa en ponderaciones."
)

dist_options = ["Normal", "Lognormal (mu, sigma)", "Gamma (k, theta)", "None (no rendida)"]


def dist_block(label: str, default_dist: str, default_params: dict, col):
    with col:
        st.markdown(f"### {label}")
        dist = st.selectbox(
            f"Distribución - {label}",
            dist_options,
            index=dist_options.index(default_dist),
            key=f"dist_{label}",
        )

        params = {}
        if dist == "Normal":
            params["mu"] = st.number_input(
                f"{label} - media (mu)",
                value=float(default_params.get("mu", 600.0)),
                step=1.0,
                key=f"{label}_mu",
            )
            params["sigma"] = st.number_input(
                f"{label} - desviación (sigma)",
                min_value=0.0,
                value=float(default_params.get("sigma", 60.0)),
                step=1.0,
                key=f"{label}_sigma",
            )
        elif dist == "Lognormal (mu, sigma)":
            params["mu_ln"] = st.number_input(
                f"{label} - mu_ln (normal subyacente)",
                value=float(default_params.get("mu_ln", 6.4)),
                step=0.01,
                key=f"{label}_mu_ln",
            )
            params["sigma_ln"] = st.number_input(
                f"{label} - sigma_ln (normal subyacente)",
                min_value=0.0,
                value=float(default_params.get("sigma_ln", 0.15)),
                step=0.01,
                key=f"{label}_sigma_ln",
            )
        elif dist == "Gamma (k, theta)":
            params["k"] = st.number_input(
                f"{label} - k (shape)",
                min_value=0.0,
                value=float(default_params.get("k", 12.0)),
                step=0.1,
                key=f"{label}_k",
            )
            params["theta"] = st.number_input(
                f"{label} - theta (scale)",
                min_value=0.0,
                value=float(default_params.get("theta", 40.0)),
                step=0.1,
                key=f"{label}_theta",
            )
        else:
            st.info("Marcada como no rendida: no se simula ni participa en ponderaciones.")
        return dist, params


c1, c2, c3, c4, c5 = st.columns(5)

m1_dist, m1_params = dist_block("Matemática I (M1)", "Normal", {"mu": 750.0, "sigma": 70.0}, c1)
m2_dist, m2_params = dist_block("Matemática II (M2)", "Normal", {"mu": 650.0, "sigma": 80.0}, c2)
len_dist, len_params = dist_block("Lenguaje", "Normal", {"mu": 650.0, "sigma": 70.0}, c3)
cie_dist, cie_params = dist_block("Ciencias", "Normal", {"mu": 650.0, "sigma": 70.0}, c4)
his_dist, his_params = dist_block("Historia", "None (no rendida)", {"mu": 650.0, "sigma": 70.0}, c5)

st.divider()


# -----------------------------
# Careers table
# -----------------------------
st.subheader("2) Posibilidades / carreras (ponderaciones + corte)")
st.write(
    "Agrega tantas filas como quieras. Las ponderaciones se interpretan como **porcentaje** (idealmente suman 100). "
    "El puntaje ponderado se calcula como:\n"
    "`(wNEM*NEM + wRANK*RANK + wM1*M1 + wM2*M2 + wLEN*LEN + wCIE*CIE + wHIS*HIS) / 100`.\n\n"
    "Si **Historia** está en **None (no rendida)**, entonces **wHIS se fuerza a 0** automáticamente."
)

default_df = pd.DataFrame(
    [
        {
            "Carrera": "Opción 1",
            "Corte": 680.0,
            "wNEM": 10.0,
            "wRANK": 20.0,
            "wM1": 20.0,
            "wM2": 20.0,
            "wLEN": 15.0,
            "wCIE": 15.0,
            "wHIS": 0.0,
        },
        {
            "Carrera": "Opción 2",
            "Corte": 720.0,
            "wNEM": 10.0,
            "wRANK": 20.0,
            "wM1": 25.0,
            "wM2": 25.0,
            "wLEN": 10.0,
            "wCIE": 10.0,
            "wHIS": 0.0,
        },
    ]
)

edited_df = st.data_editor(
    default_df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Carrera": st.column_config.TextColumn(help="Nombre de la carrera/opción"),
        "Corte": st.column_config.NumberColumn(min_value=100.0, max_value=1000.0, step=1.0),
        "wNEM": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
        "wRANK": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
        "wM1": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
        "wM2": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
        "wLEN": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
        "wCIE": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
        "wHIS": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0),
    },
)

st.divider()
run = st.button("Simular", type="primary")


# -----------------------------
# Run simulation
# -----------------------------
if run:
    base_seed = int(seed)
    n = int(n_sims)

    m1 = simulate_dist(m1_dist, n, m1_params, seed=base_seed + 1)
    m2 = simulate_dist(m2_dist, n, m2_params, seed=base_seed + 2)
    leng = simulate_dist(len_dist, n, len_params, seed=base_seed + 3)
    cien = simulate_dist(cie_dist, n, cie_params, seed=base_seed + 4)
    histo = simulate_dist(his_dist, n, his_params, seed=base_seed + 5)

    if m1 is not None:
        m1 = clamp_scores(m1)
    if m2 is not None:
        m2 = clamp_scores(m2)
    if leng is not None:
        leng = clamp_scores(leng)
    if cien is not None:
        cien = clamp_scores(cien)
    if histo is not None:
        histo = clamp_scores(histo)

    # -----------------------------
    # Histogramas por prueba
    # -----------------------------
    st.subheader("Histogramas de las pruebas simuladas")
    st.caption(f"Escala fija para todos los gráficos: X = [{int(X_MIN)}, {int(X_MAX)}]")

    cols = st.columns(5)

    def show_test_hist(col, arr, title):
        with col:
            if arr is None:
                st.info(f"{title}: no rendida")
            else:
                st.pyplot(plot_hist_basic(arr, bins=HIST_BINS, title=f"{title} (simulado)"), clear_figure=True)

    show_test_hist(cols[0], m1, "M1")
    show_test_hist(cols[1], m2, "M2")
    show_test_hist(cols[2], leng, "Lenguaje")
    show_test_hist(cols[3], cien, "Ciencias")
    show_test_hist(cols[4], histo, "Historia")

    # Arrays seguros
    m1z = nz_array(m1, n)
    m2z = nz_array(m2, n)
    lenz = nz_array(leng, n)
    ciez = nz_array(cien, n)
    hisz = nz_array(histo, n)

    his_rendida = histo is not None

    # -----------------------------
    # Evaluación por carrera
    # -----------------------------
    results = []
    plots = []
    warnings = []

    for i, row in edited_df.iterrows():
        carrera = str(row.get("Carrera", f"Opción {i+1}"))
        cut = float(row.get("Corte", np.nan))

        wNEM = float(row.get("wNEM", 0.0))
        wR = float(row.get("wRANK", 0.0))
        wM1 = float(row.get("wM1", 0.0))
        wM2 = float(row.get("wM2", 0.0))
        wL = float(row.get("wLEN", 0.0))
        wC = float(row.get("wCIE", 0.0))
        wH = float(row.get("wHIS", 0.0))

        wH_eff = wH
        if not his_rendida and wH != 0:
            wH_eff = 0.0
            warnings.append(f"'{carrera}': Historia está en None (no rendida), se fuerza wHIS=0 (tenías {wH}).")

        wsum = wNEM + wR + wM1 + wM2 + wL + wC + wH_eff
        if wsum <= 0 or not np.isfinite(cut):
            continue

        weighted = (
            (wNEM * nem)
            + (wR * ranking)
            + (wM1 * m1z)
            + (wM2 * m2z)
            + (wL * lenz)
            + (wC * ciez)
            + (wH_eff * hisz)
        ) / 100.0

        # (solo para consistencia visual; no altera el cálculo de prob si el corte está dentro de rango)
        weighted = clamp_scores(weighted)

        p_hat = float(np.mean(weighted >= cut))
        p5, p50, p95 = np.percentile(weighted, [5, 50, 95])

        results.append(
            {
                "Carrera": carrera,
                "Corte": cut,
                "Suma ponderaciones (efectiva)": wsum,
                "Prob(supera corte)": p_hat,
                "P5": p5,
                "P50": p50,
                "P95": p95,
                "E[puntaje]": float(np.mean(weighted)),
                "Std[puntaje]": float(np.std(weighted)),
            }
        )

        fig = plot_hist_with_cut(
            weighted,
            cut=cut,
            bins=HIST_BINS,
            title=f"{carrera} — Corte {cut:.0f} — P(superar)={100*p_hat:.1f}%",
        )
        plots.append((carrera, fig))

    if warnings:
        with st.expander("Avisos (ponderaciones forzadas a 0 por pruebas no rendidas)", expanded=False):
            for w in warnings:
                st.warning(w)

    if len(results) == 0:
        st.warning("No hay filas válidas para simular (revisa ponderaciones y cortes).")
    else:
        res_df = pd.DataFrame(results).sort_values("Prob(supera corte)", ascending=False)

        st.subheader("Resultados")
        st.dataframe(style_results_table(res_df), use_container_width=True)

        st.subheader("Histogramas por carrera (barras rojas sobre el umbral)")
        cols2 = st.columns(2)
        for j, (carrera, fig) in enumerate(plots):
            with cols2[j % 2]:
                st.pyplot(fig, clear_figure=True)

        st.subheader("Ranking de opciones por probabilidad (mayor → menor)")
        st.caption("Eje X: nombre de la opción (rotado vertical). Eje Y: probabilidad de superar el corte.")
        st.pyplot(plot_prob_bar(res_df), clear_figure=True)
