import streamlit as st
import numpy as np
import plotly.graph_objects as go
from scipy.spatial.distance import cdist
import matplotlib.pyplot as plt
from streamlit_plotly_events import plotly_events

# ---------- Configuración inicial ----------
st.set_page_config(layout="wide", page_title="CMDIC-GNV-SIMS")
st.title("CMDIC-GNV")

# ---------- Mostrar avatar en el sidebar ----------
import base64
from pathlib import Path

def render_sidebar_avatar(image_path):
    img_bytes = Path(image_path).read_bytes()
    encoded = base64.b64encode(img_bytes).decode()
    st.sidebar.markdown(
        f"""
        <div style='display: flex; justify-content: center; margin-bottom: 10px; margin-top: -5px;'>
            <img src='data:image/jpeg;base64,{encoded}'
                 style='border-radius: 50%; width: 100px; height: 100px; object-fit: cover;
                        box-shadow: 0 0 6px rgba(0,0,0,0.3); border: 1px solid #333;' />
        </div>
        """,
        unsafe_allow_html=True
    )



L = 500
x_domain = np.arange(L)

# ---------- Modelos de covarianza y variograma ----------
def spherical_cov(h, range_, nugget=0.0, sill=1.0):
    h = np.abs(h)
    c = np.where(h < range_,
                 sill * (1 - 1.5 * (h / range_) + 0.5 * (h / range_)**3),
                 0.0)
    return c + nugget * (h == 0)

def exponential_cov(h, range_, nugget=0.0, sill=1.0):
    h = np.abs(h)
    return sill * np.exp(-3 * h / range_) + nugget * (h == 0)

def gaussian_cov(h, range_, nugget=0.0, sill=1.0):
    h = np.abs(h)
    return sill * np.exp(-3 * (h**2) / (range_**2)) + nugget * (h == 0)

model_dict = {
    "Esférico": spherical_cov,
    "Exponencial": exponential_cov,
    "Gaussiano": gaussian_cov
}

# ---------- Realización base ----------
# También se almacenarán la versión original gaussiana y los valores originales de las muestras (antes de offset y transformaciones)
@st.cache_data
def generate_reference_realization(model_name, range_, nugget, use_seed):
    if use_seed:
        np.random.seed(42)
    else:
        np.random.seed(None)
    cov_func = model_dict[model_name]
    C = cov_func(cdist(x_domain.reshape(-1, 1), x_domain.reshape(-1, 1)), range_, nugget)
    L_chol = np.linalg.cholesky(C + 1e-10 * np.eye(L))
    z = np.random.randn(L)
    return L_chol @ z

# ---------- Interfaz lateral ----------
with st.sidebar:
    render_sidebar_avatar("avatar_neutral.jpg")
    st.header("⚙️ Parámetros del Variograma")
    model_name = st.selectbox("Modelo", list(model_dict.keys()), key="model")
    range_ = st.slider("🔏 Alcance (range)", 10, 200, 50, key="range")
    nugget = st.slider("💥 Pepita (nugget)", 0.0, 1.0, 0.1, key="nugget")
    kriging_type = st.radio("🧠 Tipo de kriging", ["Ordinario", "Simple"], key="kriging_type")
    mean_value = st.number_input("Valor medio (Kriging Simple)", value=0.0, key="mean_value") if kriging_type == "Simple" else None

    # Mostrar gráfico de covarianza y variograma inmediatamente después de "pepita"
    sill_structural = 1.0 - nugget
    cov_func = model_dict[model_name]
    h_max = 200
    h_vals = np.linspace(0, h_max, 200)
    cov_vals = cov_func(h_vals, range_, nugget=nugget, sill=sill_structural)
    vario_vals = cov_vals[0] - cov_vals

    fig_vario, ax = plt.subplots(figsize=(5, 3))
    ax.plot(h_vals, cov_vals, label="Covarianza C(h)", color='blue')
    ax.plot(h_vals, vario_vals, label="Variograma γ(h)", color='green')
    ax.set_xlabel("Distancia h")
    ax.set_ylabel("Valor")
    ax.set_title("Covarianza y Variograma")
    ax.set_xlim(0, h_max)
    ax.grid(True)
    ax.legend()
    st.pyplot(fig_vario)

    st.markdown("---")

    estimate_btn = st.button("📍 Estimar")
    simulate_btn = st.button("🌺 Simular")
    if simulate_btn:
        if not st.session_state.points:
            st.session_state.avatar_path = "avatar_frustrado.jpg"
    else:
        st.session_state.avatar_path = "avatar_feliz.jpg"

    reset_btn = st.button("🧼 Borrar puntos")


    st.header("📊 Mostrar en el gráfico")
    show_highlight = st.checkbox("Destacar una realización")
    if show_highlight:
        selected_index = st.number_input("Índice de realización", min_value=0, max_value=99, value=0)
    st.markdown("---")
    show_realization = st.checkbox("Realidad Desconocida", value=True)
    show_kriging = st.checkbox("Kriging", value=True)
    show_samples = st.checkbox("Muestras", value=True)
    show_simulations = st.checkbox("Simulaciones", value=True)
    show_mean = st.checkbox("Promedio", value=True)
    show_band90 = st.checkbox("Banda 90%", value=False)
    show_band50 = st.checkbox("Banda 50%", value=False)
    show_band_minmax = st.checkbox("Banda Min–Máx", value=False)

    st.markdown("---")
    st.header("📌 Postprocesos")

    cutoff_threshold = st.number_input("Umbral de corte", value=0.8, step=0.05, format="%.2f", key="cutoff")

    show_stddev = st.checkbox("Mostrar desviación estándar", value=True)
    show_prob = st.checkbox("Mostrar probabilidad sobre umbral", value=True)
    show_mean_above = st.checkbox("Mostrar ley media sobre umbral", value=True)

# ---------- Estado ----------
if "original_data_values" not in st.session_state:
    st.session_state.original_data_values = []
if "points" not in st.session_state:
    st.session_state.points = []
if "simulations" not in st.session_state:
    st.session_state.simulations = None

# Forzar regeneración si cambian parámetros clave
param_combo = (model_name, range_, nugget)
if "last_param_combo" not in st.session_state or st.session_state.last_param_combo != param_combo:
    st.session_state.last_param_combo = param_combo
    st.session_state.realization_gaussian = generate_reference_realization(model_name, range_, nugget, use_seed=True)
    st.session_state.realization = st.session_state.realization_gaussian.copy()
    st.session_state.offset = -np.min(st.session_state.realization) + 0.05
    st.session_state.realization = st.session_state.realization + 4.55

    if st.session_state.points:
        st.session_state.original_data_values = [st.session_state.realization_gaussian[x] for x, _ in st.session_state.points]
        st.session_state.points = [(x, st.session_state.realization[x]) for x, _ in st.session_state.points]

        # Forzar recalculo inmediato de estimación y simulaciones
        st.session_state.simulations = None
        st.session_state.force_reestimate = True
    # Actualizar las muestras con los nuevos valores
    if st.session_state.points:
        st.session_state.original_data_values = [st.session_state.realization_gaussian[x] for x, _ in st.session_state.points]
        st.session_state.points = [(x, st.session_state.realization[x]) for x, _ in st.session_state.points]

realization = st.session_state.realization
offset = st.session_state.offset

# ---------- Captura de clics ----------
fig_for_clicks = go.Figure()
fig_for_clicks.add_trace(go.Scatter(x=x_domain, y=realization, mode='lines', name='Realidad Desconocida', line=dict(color='black')))
if st.session_state.points:
    fig_for_clicks.add_trace(go.Scatter(
        x=[p[0] for p in st.session_state.points],
        y=[p[1] + 0.0 for p in st.session_state.points],  # ya incluyen desplazamiento visual global
        mode='markers', marker=dict(color='red', size=8), name='Muestras'
    ))
fig_for_clicks.update_layout(clickmode='event+select')

click_result = plotly_events(
    fig_for_clicks,
    click_event=True,
    select_event=False,
    hover_event=False,
    override_height=300,
    override_width="100%"
)

if click_result:
    x_click = int(round(click_result[0]['x']))
    if 0 <= x_click < L and x_click not in [p[0] for p in st.session_state.points]:
        st.session_state.points.append((x_click, realization[x_click]))
        st.rerun()

if reset_btn:
    st.session_state.points = []
    st.session_state.simulations = None
    st.rerun()

# ---------- Preparar trazos para el gráfico principal ----------
scatter_traces = []

# 1. Simulaciones y bandas (al fondo)
if st.session_state.simulations is not None:
    sims = st.session_state.simulations

    if show_simulations:
        for sim in sims:
            scatter_traces.append(go.Scatter(x=x_domain, y=sim, mode='lines', line=dict(color='gray', width=1), opacity=0.2, showlegend=False))

    if show_band90:
        p5 = np.nanpercentile(sims, 5, axis=0)
        p95 = np.nanpercentile(sims, 95, axis=0)
        scatter_traces.append(go.Scatter(x=x_domain, y=p5, fill=None, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False))
        scatter_traces.append(go.Scatter(x=x_domain, y=p95, fill='tonexty', mode='lines', name='Banda 90%', line=dict(color='rgba(255,255,0,0.3)')))

    if show_band50:
        p25 = np.nanpercentile(sims, 25, axis=0)
        p75 = np.nanpercentile(sims, 75, axis=0)
        scatter_traces.append(go.Scatter(x=x_domain, y=p25, fill=None, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False))
        scatter_traces.append(go.Scatter(x=x_domain, y=p75, fill='tonexty', mode='lines', name='Banda 50%', line=dict(color='rgba(0,255,0,0.3)')))

    if show_mean:
        mean_sim = np.mean(sims, axis=0)
        scatter_traces.append(go.Scatter(x=x_domain, y=mean_sim, mode='lines', name='Promedio', line=dict(color='black', dash='dash')))
if show_realization:
    scatter_traces.append(go.Scatter(x=x_domain, y=realization, mode='lines', name='Realización', line=dict(color='lightgray')))



# ---------- Kriging ----------
if (estimate_btn or st.session_state.get("force_reestimate")) and len(st.session_state.points) > 0:
    x_sample = np.array([p[0] for p in st.session_state.points])
    y_sample = np.array([p[1] for p in st.session_state.points])
    C = cov_func(np.abs(x_sample[:, None] - x_sample[None, :]), range_, nugget)
    c = cov_func(np.abs(x_domain[:, None] - x_sample[None, :]), range_, nugget)

    if kriging_type == "Ordinario":
        ones = np.ones((len(x_sample), 1))
        A = np.block([[C, ones], [ones.T, np.zeros((1,1))]])
        rhs = np.vstack([c.T, np.ones((1, L))])
        weights = np.linalg.solve(A, rhs)[0:-1]
        estimation = weights.T @ y_sample
    else:
        C_inv = np.linalg.inv(C)
        weights = c @ C_inv
        estimation = mean_value + weights @ (y_sample - mean_value)

    if show_kriging:
        scatter_traces.append(go.Scatter(x=x_domain, y=estimation, name=f"Kriging {kriging_type}", line=dict(color='blue')))

# ---------- Simulaciones condicionales ----------
if simulate_btn:
    st.session_state.force_reestimate = True
    st.session_state.simulations = None
    scatter_traces = []
if (simulate_btn or st.session_state.get("force_reestimate")) and len(st.session_state.points) > 0:
    scatter_traces = []
    x_sample = np.array([p[0] for p in st.session_state.points])
    y_gaussian = np.array(st.session_state.original_data_values)
    C = cov_func(np.abs(x_sample[:, None] - x_sample[None, :]), range_, nugget)
    c = cov_func(np.abs(x_domain[:, None] - x_sample[None, :]), range_, nugget)
    C_inv = np.linalg.inv(C)
    residual_cov = cov_func(np.abs(x_domain[:, None] - x_domain[None, :]), range_, nugget)
    L_chol = np.linalg.cholesky(residual_cov + 1e-10 * np.eye(L))

    simulations = []
    for _ in range(100):
        z_nc = L_chol @ np.random.randn(L)  # Simulación no condicional

        # Calcular residuos: diferencia entre referencia y simulación no condicional en puntos muestrales
        residuals = st.session_state.realization_gaussian[x_sample] - z_nc[x_sample]

        # Kriging de residuos
        if kriging_type == "Ordinario":
            ones = np.ones((len(x_sample), 1))
            A = np.block([[C, ones], [ones.T, np.zeros((1,1))]])
            rhs = np.vstack([c.T, np.ones((1, L))])
            weights = np.linalg.solve(A, rhs)[0:-1]
            residual_field = weights.T @ residuals
        else:
            weights = c @ C_inv
            residual_field = weights @ residuals

        # Simulación condicional
        sim_cond = z_nc + residual_field

        # Transformar para visualización con mínimo global de -4.5
        sim_cond = sim_cond + 4.55
        simulations.append(sim_cond)

    st.session_state.simulations = np.array(simulations)

# ---------- Mostrar simulaciones ----------
if st.session_state.simulations is not None:
    sims = st.session_state.simulations

    # 1. Simulaciones (al fondo)
    if show_simulations:
        for sim in sims:
            scatter_traces.append(go.Scatter(x=x_domain, y=sim, mode='lines', line=dict(color='gray', width=1), opacity=0.2, showlegend=False))

    # 2. Bandas
    # 5. Banda Min–Máx (rojo)
    if show_band_minmax:
        min_vals = np.min(sims, axis=0)
        max_vals = np.max(sims, axis=0)
        scatter_traces.append(go.Scatter(x=x_domain, y=min_vals, fill=None, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False))
        scatter_traces.append(go.Scatter(x=x_domain, y=max_vals, fill='tonexty', mode='lines', name='Rango total de realizaciones', line=dict(color='rgba(255,0,0,0.2)')))

    if show_band90:
        p5 = np.nanpercentile(sims, 5, axis=0)
        p95 = np.nanpercentile(sims, 95, axis=0)
        scatter_traces.append(go.Scatter(x=x_domain, y=p5, fill=None, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False))
        scatter_traces.append(go.Scatter(x=x_domain, y=p95, fill='tonexty', mode='lines', name='Banda 90%', line=dict(color='rgba(100,100,255,0.2)')))

    if show_band50:
        p25 = np.nanpercentile(sims, 25, axis=0)
        p75 = np.nanpercentile(sims, 75, axis=0)
        scatter_traces.append(go.Scatter(x=x_domain, y=p25, fill=None, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False))
        scatter_traces.append(go.Scatter(x=x_domain, y=p75, fill='tonexty', mode='lines', name='Banda 50%', line=dict(color='rgba(150,150,150,0.3)')))

    # 3. Promedio
    if show_mean:
        mean_sim = np.mean(sims, axis=0)
        scatter_traces.append(go.Scatter(x=x_domain, y=mean_sim, mode='lines', name='Promedio', line=dict(color='purple')))

# 4. Muestras (encima de todo)
if show_samples:
    scatter_traces.append(go.Scatter(
        x=[p[0] for p in st.session_state.points],
        y=[p[1] for p in st.session_state.points],
        mode='markers', name='Muestras', marker=dict(color='red', size=8),
        showlegend=True
    ))



# Limpiar bandera de reestimación
if len(st.session_state.points) == 0:
    st.session_state.simulations = None
st.session_state.force_reestimate = False

# 6. Realización destacada
if st.session_state.simulations is not None and show_highlight:
    try:
        sim_to_highlight = st.session_state.simulations[selected_index]
        scatter_traces.append(go.Scatter(
            x=x_domain,
            y=sim_to_highlight,
            mode='lines',
            name='Realización destacada',
            line=dict(color='white', width=3),
            showlegend=True
        ))
    except IndexError:
        st.warning("El índice de realización destacada está fuera de rango.")

# Mostrar gráfica final
fig = go.Figure(data=scatter_traces)
fig.update_layout(title="Proceso + Estimación + Simulaciones", xaxis_title="Coordenada", yaxis_title="Valor", height=600)
st.plotly_chart(fig, use_container_width=True)
# ---------- Postprocesos ----------
if st.session_state.simulations is not None:
    sims = st.session_state.simulations
    std_dev = np.std(sims, axis=0)
    prob_above = np.mean(sims > cutoff_threshold, axis=0)

    with np.errstate(divide='ignore', invalid='ignore'):
        mask = sims > cutoff_threshold
        sum_vals = np.sum(sims * mask, axis=0)
        count_vals = np.sum(mask, axis=0)
        mean_above = sum_vals / count_vals
        mean_above[count_vals == 0] = np.nan  # Interrumpir curva donde no hay datos sobre el umbral

    # Decidir en qué eje va la desviación estándar
    stddev_yaxis = 'y2' if np.max(std_dev) <= 1.1 else 'y'

    post_traces = []

    if show_stddev:
        post_traces.append(go.Scatter(
            x=x_domain, y=std_dev, name="Desviación estándar",
            line=dict(color='orange', dash='dash'), yaxis=stddev_yaxis
        ))

    if show_mean_above:
        post_traces.append(go.Scatter(
            x=x_domain, y=mean_above, name=f"Media cond. (Y > {cutoff_threshold})",
            line=dict(color='blue'), yaxis='y'
        ))

    if show_prob:
        post_traces.append(go.Scatter(
            x=x_domain, y=prob_above, name=f"P(Y > {cutoff_threshold})",
            line=dict(color='green', dash='dot'), yaxis='y2'
        ))

    if post_traces:
        fig_post = go.Figure(data=post_traces)
        fig_post.update_layout(
            title="📌 Postprocesos sobre simulaciones",
            xaxis_title="Coordenada",
            yaxis=dict(title="Valor (media condicional)", side='left'),
            yaxis2=dict(title="Probabilidad / std", overlaying='y', side='right', range=[0, 1.1]),
            height=400
        )
        st.plotly_chart(fig_post, use_container_width=True)

# ---------- Curva Tonelaje–Ley ----------
with st.container():
    st.markdown("## 📉 Curva Tonelaje–Ley")

col1, col2 = st.columns([5, 2])  # Gráfico a la izquierda, controles a la derecha

with col2:
    st.markdown("### 🎚️ Parámetros de Corte")
    col_min, col_max, col_step = st.columns(3)
    with col_min:
        cutoff_min = st.number_input("Corte mínimo", value=4.0, step=0.1, format="%.2f")
    with col_max:
        cutoff_max = st.number_input("Corte máximo", value=7.0, step=0.1, format="%.2f")
    with col_step:
        cutoff_step = st.number_input("Paso", value=0.1, step=0.05, format="%.2f")

    st.markdown("### 📊 Mostrar curvas")
    show_gt_sims = st.checkbox("Mostrar GT de sims", value=True)
    show_band90_tl = st.checkbox("Banda 90%", value=True)
    show_band50_tl = st.checkbox("Banda 50%", value=True)
    show_minmax_tl = st.checkbox("Min–Máx", value=False)
    show_expected_tl = st.checkbox("Promedio simulaciones", value=True)
    show_kriging_curve = st.checkbox("Curva sobre kriging", value=True)
    show_mean_curve = st.checkbox("Curva sobre media sim.", value=False)

cutoff_values = np.arange(cutoff_min, cutoff_max + cutoff_step, cutoff_step)


# --- Corte específico para análisis ---
selected_cutoff = st.selectbox("Seleccionar corte para histogramas", cutoff_values)
cutoff_idx = np.where(np.isclose(cutoff_values, selected_cutoff))[0][0]


if st.session_state.simulations is not None:
    sims = st.session_state.simulations
    n_sim, n_nodes = sims.shape

    tonelajes = []
    leyes = []

    for sim in sims:
        ton = np.mean(sim[None, :] > cutoff_values[:, None], axis=1)
        with np.errstate(divide='ignore', invalid='ignore'):
            ley = np.sum(sim[None, :] * (sim[None, :] > cutoff_values[:, None]), axis=1) / \
                  np.sum(sim[None, :] > cutoff_values[:, None], axis=1)
        ley[np.isnan(ley)] = np.nan
        tonelajes.append(ton)
        leyes.append(ley)

    tonelajes = np.array(tonelajes)  # shape (n_sim, n_cutoff)
    leyes = np.array(leyes)

    fig_ton_law = go.Figure()

    for i in range(len(leyes)):
        fig_ton_law.add_trace(go.Scatter(
        x=cutoff_values,
        y=leyes[i],
        mode='lines',
        line=dict(width=1, color='rgba(255,255,255,0.05)'),
        showlegend=False,
        yaxis='y2'
    ))
    
    if show_gt_sims:
        for i in range(len(leyes)):
            fig_ton_law.add_trace(go.Scatter(
                x=cutoff_values,
                y=leyes[i],
                mode='lines',
                line=dict(width=1, color='rgba(255,255,255,0.05)'),
                showlegend=False,
                yaxis='y2'
            ))
        for i in range(len(tonelajes)):
            fig_ton_law.add_trace(go.Scatter(
                x=cutoff_values,
                y=tonelajes[i],
                mode='lines',
                line=dict(width=1, color='rgba(255,255,255,0.05)'),
                showlegend=False,
                yaxis='y'
            ))

    
    if show_gt_sims:
        for i in range(len(leyes)):
            fig_ton_law.add_trace(go.Scatter(
                x=cutoff_values,
                y=leyes[i],
                mode='lines',
                line=dict(width=1, color='rgba(255,255,255,0.05)'),
                showlegend=False,
                yaxis='y2'
            ))
        for i in range(len(tonelajes)):
            fig_ton_law.add_trace(go.Scatter(
                x=cutoff_values,
                y=tonelajes[i],
                mode='lines',
                line=dict(width=1, color='rgba(255,255,255,0.05)'),
                showlegend=False,
                yaxis='y'
            ))

    # Bandas
    if show_band90_tl:
        p5 = np.nanpercentile(tonelajes, 5, axis=0)
        p95 = np.nanpercentile(tonelajes, 95, axis=0)
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=p5, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False, yaxis='y'))
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=p95, fill='tonexty', name='Banda 90% Tonelaje', line=dict(color='rgba(255,255,0,0.3)'), yaxis='y'))

        p5_ley = np.nanpercentile(leyes, 5, axis=0)
        p95_ley = np.nanpercentile(leyes, 95, axis=0)
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=p5_ley, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False, yaxis='y2'))
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=p95_ley, fill='tonexty', name='Banda 90% Ley', line=dict(color='rgba(255,255,0,0.3)'), yaxis='y2'))

    if show_band50_tl:
        p25 = np.nanpercentile(tonelajes, 25, axis=0)
        p75 = np.nanpercentile(tonelajes, 75, axis=0)
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=p25, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False, yaxis='y'))
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=p75, fill='tonexty', name='Banda 50% Tonelaje', line=dict(color='rgba(0,255,0,0.3)'), yaxis='y'))

        p25_ley = np.nanpercentile(leyes, 25, axis=0)
        p75_ley = np.nanpercentile(leyes, 75, axis=0)
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=p25_ley, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False, yaxis='y2'))
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=p75_ley, fill='tonexty', name='Banda 50% Ley', line=dict(color='rgba(0,255,0,0.3)'), yaxis='y2'))

    if show_minmax_tl:
        min_ton = np.nanmin(tonelajes, axis=0)
        max_ton = np.nanmax(tonelajes, axis=0)
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=min_ton, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False, yaxis='y'))
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=max_ton, fill='tonexty', name='Rango total Tonelaje', line=dict(color='rgba(255,0,0,0.2)'), yaxis='y'))

        min_ley = np.nanmin(leyes, axis=0)
        max_ley = np.nanmax(leyes, axis=0)
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=min_ley, mode='lines', line=dict(color='rgba(0,0,0,0)'), showlegend=False, yaxis='y2'))
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=max_ley, fill='tonexty', name='Rango total Ley', line=dict(color='rgba(255,0,0,0.2)'), yaxis='y2'))

    # Promedio de simulaciones
    if show_expected_tl:
        ton_mean = np.mean(tonelajes, axis=0)
        ley_mean = np.nanmean(leyes, axis=0)
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=ton_mean, name='E[Tonelaje]', line=dict(color='blue'), yaxis='y'))
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=ley_mean, name='E[Ley]', line=dict(color='green'), yaxis='y2'))

    # Media de simulaciones (campo promedio)
    if show_mean_curve:
        mean_field = np.mean(sims, axis=0)
        ton_mean_field = np.mean(mean_field[None, :] > cutoff_values[:, None], axis=1)
        with np.errstate(divide='ignore', invalid='ignore'):
            ley_mean_field = np.sum(mean_field[None, :] * (mean_field[None, :] > cutoff_values[:, None]), axis=1) / \
                             np.sum(mean_field[None, :] > cutoff_values[:, None], axis=1)
            ley_mean_field[np.isnan(ley_mean_field)] = np.nan
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=ton_mean_field, name='Media campo (Ton)', line=dict(color='blue', dash='dot'), yaxis='y'))
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=ley_mean_field, name='Media campo (Ley)', line=dict(color='green', dash='dot'), yaxis='y2'))

    # Kriging (si existe)
    
    if show_kriging_curve and ("kriging_curve_ready" not in st.session_state or not st.session_state.kriging_curve_ready):
        estimate_btn = True
        st.session_state.force_reestimate = True
        st.session_state.kriging_curve_ready = True

    if 'points' in st.session_state and st.session_state.points:
        x_sample = np.array([p[0] for p in st.session_state.points])
        y_sample = np.array([p[1] for p in st.session_state.points])
        c = cov_func(np.abs(x_domain[:, None] - x_sample[None, :]), range_, nugget)
        C = cov_func(np.abs(x_sample[:, None] - x_sample[None, :]), range_, nugget)

        if kriging_type == "Ordinario":
            ones = np.ones((len(x_sample), 1))
            A = np.block([[C, ones], [ones.T, np.zeros((1, 1))]])
            rhs = np.vstack([c.T, np.ones((1, L))])
            weights = np.linalg.solve(A, rhs)[0:-1]
            krig = weights.T @ y_sample
        else:
            C_inv = np.linalg.inv(C)
            weights = c @ C_inv
            krig = mean_value + weights @ (y_sample - mean_value)

        ton_krig = np.mean(krig[None, :] > cutoff_values[:, None], axis=1)
        with np.errstate(divide='ignore', invalid='ignore'):
            ley_krig = np.sum(krig[None, :] * (krig[None, :] > cutoff_values[:, None]), axis=1) / \
                       np.sum(krig[None, :] > cutoff_values[:, None], axis=1)
            ley_krig[np.isnan(ley_krig)] = np.nan

        
    if show_kriging_curve:
        fig_ton_law.add_trace(go.Scatter(x=cutoff_values, y=ton_krig, name='Kriging (Ton)', line=dict(color='blue', dash='dash'), yaxis='y'))
        

        

    # Configuración de ejes
    fig_ton_law.add_vline(x=selected_cutoff, line_dash="dot", line_color="white", line_width=2)

    fig_ton_law.update_layout(
        title="Curva Tonelaje–Ley",
        xaxis_title="Corte",
        yaxis=dict(title="Tonelaje (> corte)", side='left', range=[0, 1]),
        yaxis2=dict(title="Ley media condicional", overlaying='y', side='right'),
        height=700
    )

    with col1:
        st.plotly_chart(fig_ton_law, use_container_width=True)

if estimate_btn and len(st.session_state.points) == 0:
    st.warning("Colega, muestrea al menos un punto.")
if simulate_btn and len(st.session_state.points) == 0:
    st.warning("Colega, perfore al menos un sondaje.")
    










# ---------- Histogramas con alineación visual y etiquetas reales ----------
if st.session_state.simulations is not None:
    ton_vals = tonelajes[:, cutoff_idx]
    ley_vals = leyes[:, cutoff_idx]

    ton_vals_clean = ton_vals[~np.isnan(ton_vals)]
    ley_vals_clean = ley_vals[~np.isnan(ley_vals)]

    def build_bins_percentiles(values, total_bins=35):
        percentiles = {p: np.nanpercentile(values, p) for p in [0, 5, 25, 50, 75, 95, 100]}
        anchors = [percentiles[p] for p in [0, 5, 25, 75, 95, 100]]
        sections = [(anchors[i], anchors[i+1]) for i in range(len(anchors)-1)]
        remaining_bins = total_bins - len(anchors)
        per_section = max(1, remaining_bins // len(sections))
        bins = []
        for (start, end) in sections:
            inner_bins = np.linspace(start, end, per_section + 2)[:-1]
            bins.extend(inner_bins.tolist())
        bins.append(percentiles[100])
        return np.unique(np.array(bins)), percentiles

    def normalize_values(values, p0, p100):
        return (values - p0) / (p100 - p0 + 1e-10)

    bins_ton, perc_ton = build_bins_percentiles(ton_vals_clean)
    bins_ley, perc_ley = build_bins_percentiles(ley_vals_clean)

    norm_bins_ton = normalize_values(bins_ton, perc_ton[0], perc_ton[100])
    norm_bins_ley = normalize_values(bins_ley, perc_ley[0], perc_ley[100])

    centers_ton = 0.5 * (norm_bins_ton[:-1] + norm_bins_ton[1:])
    centers_ley = 0.5 * (norm_bins_ley[:-1] + norm_bins_ley[1:])

    hist_ton, _ = np.histogram(ton_vals_clean, bins=bins_ton)
    hist_ley, _ = np.histogram(ley_vals_clean, bins=bins_ley)

    def compute_shapes():
        return [
            go.layout.Shape(type="rect", x0=0.0, x1=1.0, y0=0, y1=1, xref='paper', yref='paper', fillcolor="rgba(255,0,0,0.2)", layer="below"),
            go.layout.Shape(type="rect", x0=0.05, x1=0.95, y0=0, y1=1, xref='paper', yref='paper', fillcolor="rgba(255,255,0,0.3)", layer="below"),
            go.layout.Shape(type="rect", x0=0.25, x1=0.75, y0=0, y1=1, xref='paper', yref='paper', fillcolor="rgba(0,255,0,0.3)", layer="below")
        ]

    def maybe_line(fig, val, p0, p100, color, dash):
        rel = (val - p0) / (p100 - p0 + 1e-10)
        fig.add_shape(type="line", x0=rel, x1=rel, y0=0, y1=1, xref="paper", yref="paper", line=dict(color=color, dash=dash, width=2))

    show_mean = show_mean_curve
    show_krig = show_kriging_curve

    tickvals = [0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0]

    # Tonelaje
    fig_hist_ton = go.Figure()
    for s in compute_shapes():
        fig_hist_ton.add_shape(s)
    fig_hist_ton.add_trace(go.Bar(x=centers_ton, y=hist_ton, marker_color="gray", width=(norm_bins_ton[1]-norm_bins_ton[0])*0.9, name="Tonelaje"))
    if show_mean:
        maybe_line(fig_hist_ton, np.nanmean(ton_vals_clean), perc_ton[0], perc_ton[100], "black", "dot")
    if show_krig:
        maybe_line(fig_hist_ton, ton_krig[cutoff_idx], perc_ton[0], perc_ton[100], "blue", "dash")
    fig_hist_ton.update_layout(
        title="Distribución Tonelaje (> corte)",
        xaxis=dict(
            title="Tonelaje",
            tickvals=tickvals,
            ticktext=[f"{perc_ton[p]:.2f}" for p in [0, 5, 25, 50, 75, 95, 100]]
        ),
        yaxis_title="Frecuencia",
        bargap=0
    )

    # Ley
    fig_hist_ley = go.Figure()
    for s in compute_shapes():
        fig_hist_ley.add_shape(s)
    fig_hist_ley.add_trace(go.Bar(x=centers_ley, y=hist_ley, marker_color="gray", width=(norm_bins_ley[1]-norm_bins_ley[0])*0.9, name="Ley"))
    if show_mean:
        maybe_line(fig_hist_ley, np.nanmean(ley_vals_clean), perc_ley[0], perc_ley[100], "black", "dot")
    if show_krig:
        maybe_line(fig_hist_ley, ley_krig[cutoff_idx], perc_ley[0], perc_ley[100], "blue", "dash")
    fig_hist_ley.update_layout(
        title="Distribución Ley condicional",
        xaxis=dict(
            title="Ley media condicional",
            tickvals=tickvals,
            ticktext=[f"{perc_ley[p]:.2f}" for p in [0, 5, 25, 50, 75, 95, 100]]
        ),
        yaxis_title="Frecuencia",
        bargap=0
    )

    st.plotly_chart(fig_hist_ton, use_container_width=True)
    st.plotly_chart(fig_hist_ley, use_container_width=True)
