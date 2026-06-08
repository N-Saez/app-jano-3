import streamlit as st
import numpy as np
import plotly.graph_objects as go
import base64
from scipy.stats import linregress
from pathlib import Path

st.set_page_config(layout="wide", page_title="CMDIC-GNV-MCS")
st.title("🔢 Taller CMDIC-GNV Generador Congruencial Lineal y Simulación Monte Carlo")

# ---------- Sidebar: Avatar y parámetros del generador ----------
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

render_sidebar_avatar("avatar_neutral.jpg")

st.sidebar.header("⚙️ Parámetros del Generador Congruencial")

X0 = st.sidebar.number_input("Semilla inicial (X₀)", min_value=0, value=1)
a = st.sidebar.number_input("Multiplicador (a)", min_value=0, value=5)
b = st.sidebar.number_input("Incremento (b)", min_value=0, value=1)
m = st.sidebar.number_input("Módulo (m)", min_value=1, value=16)
n = st.sidebar.number_input("Cantidad de números a generar", min_value=10, value=1000)

mostrar_tabla_btn = st.sidebar.button("📋 Mostrar 10 iteraciones")
simular_btn = st.sidebar.button("🎰 Simular secuencia completa")

# ---------- Introducción y explicación del generador ----------
st.markdown("## 📖 Introducción")
st.latex(r"x_{n+1} \equiv (a x_n + b) \mod m \quad 	\text{con } n \geq 0")
st.markdown("""
<div style='font-size: 18px;'>
<b>Nota:</b> El símbolo <code>≡</code> indica una <b>congruencia</b>: dos números son congruentes módulo <code>m</code> si al dividirlos por <code>m</code> el residuo es el mismo.<br>
Por ejemplo, <code>17 ≡ 2 mod 5</code> porque <b>17 dividido por 5 da residuo 2</b>, y <b>2 dividido por 5 también da residuo 2</b>. Ambos números dejan el mismo resto cuando se dividen por 5.
</div>
""", unsafe_allow_html=True)

st.latex(r"U_n =  \frac{x_n}{m}")
st.markdown("""
<div style='font-size: 18px;'>
 <code>U_n</code> es el número aleatorio <i>normalizado</i> que se obtiene dividiendo el valor <code>xₙ</code> por el módulo <code>m</code>, lo que garantiza que esté en el intervalo [0, 1).
</div>
""", unsafe_allow_html=True)
st.markdown("---")
st.markdown("### 🧮 Primeras 10 iteraciones")

if mostrar_tabla_btn:
    
    X_preview = [X0]
    U_preview = [X0 / m]
    for _ in range(9):
        xn = (a * X_preview[-1] + b) % m
        X_preview.append(xn)
        U_preview.append(xn / m)

    import pandas as pd
    df_preview = pd.DataFrame({
        "n":  list(range(1, 10)),
        "Modulo": m,
        "Mult": a,
        "xₙ₋₁": [X_preview[i - 1] if i > 0 else None for i in range(1,10)],
        "Inc": b,
        "a·xₙ₋₁ + b": [a * X_preview[i - 1] + b if i > 0 else None for i in range(1,10)],
        "Parte entera \n(a·xₙ₋₁ + b) / m": [int((a * X_preview[i - 1] + b) // m) if i > 0 else None for i in range(1,10)],
        "Resto xₙ \n(a·xₙ₋₁ + b) mod m)": [int((a * X_preview[i - 1] + b) % m) if i > 0 else int(X_preview[0] % m) for i in range(1,10)],
        "N Aleatorio \nUₙ = xₙ / m": [U_preview[i]  if i > 0 else None for i in range(1,10) ],
    })
    st.markdown(
        """
        <style>
        table {margin-left: auto; margin-right: auto; font-size: 16px; text-align: center;}
        th, td {text-align: center !important; padding: 6px 12px;}
        </style>
        """, unsafe_allow_html=True)

    st.markdown(
    df_preview.to_html(index=False, escape=False, justify='center'),
    unsafe_allow_html=True
    )






if simular_btn:
  # ---------- Generación de secuencia ----------
    X = np.zeros(n)
    U = np.zeros(n)
    X[0] = X0
    for i in range(1, n):
        X[i] = (a * X[i - 1] + b) % m
    U = X / m


    st.markdown("---")
# ---------- Gráficos organizados en columnas ----------
    fig_seq = go.Figure()
    fig_seq.add_trace(go.Scatter(y=[U[i] for i in range(1,999)], mode='lines+markers', name='Uᵢ'))
    fig_seq.update_layout(title="📈 Secuencia generada (Uᵢ)", xaxis_title="i", yaxis_title="Uᵢ", height=400)
    st.plotly_chart(fig_seq, use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=[U[i] for i in range(1,999)], nbinsx=50, marker=dict(color='lightblue', line=dict(color='black', width=1))))
        fig_hist.update_layout(title="📊 Histograma de Uᵢ", xaxis_title="Valor", yaxis_title="Frecuencia", height=500)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col2:
  

    # ---------- Gráfico de pares consecutivos ----------
        fig_pairs = go.Figure()
        fig_pairs.add_trace(go.Scatter(x=U[:-1], y=U[1:], mode='markers', marker=dict(size=4, color='red')))
        slope, intercept, r_value, _, _ = linregress(U[:-1], U[1:])
        fig_pairs.add_trace(go.Scatter(
        x=U[:-1],
        y=slope * U[:-1] + intercept,
        mode='lines',
        line=dict(color='blue', dash='dash'),
        name=f"Regresión: r = {r_value:.2f}, R² = {r_value**2:.2f}"
        ))
        fig_pairs.update_layout(
        title="🔁 Diagrama de pares (Uᵢ, Uᵢ₊₁)",
        xaxis=dict(title="Uᵢ", range=[0, 1], scaleanchor="y", scaleratio=1, constrain='range'),
        yaxis=dict(title="Uᵢ₊₁", range=[0, 1], constrain='range'),
        height=500
        )
        st.plotly_chart(fig_pairs, use_container_width=True)


# ---------- Simulación Monte Carlo ----------
st.markdown("---")
st.markdown("## 🎲 Simulación Monte Carlo")

from scipy.stats import expon, norm, lognorm

def ecdf(data):
    x = np.sort(data)
    y = np.arange(1, len(data)+1) / len(data)
    return x, y

st.sidebar.header("📐 Distribución de referencia")
dist_name = st.sidebar.selectbox("Selecciona una distribución:", ["Exponencial", "Normal", "Log-Normal"])
sim_montecarlo = st.sidebar.button("▶️ Simular Monte Carlo")

if sim_montecarlo:
    X = np.zeros(n)
    U = np.zeros(n)
    X[0] = X0
    for i in range(1, n):
        X[i] = (a * X[i - 1] + b) % m
    U = X / m

    if dist_name == "Exponencial":
        ref_samples = expon.rvs(size=n)
        cdf_func = expon.cdf
        ppf_func = expon.ppf
    elif dist_name == "Normal":
        ref_samples = norm.rvs(size=n)
        cdf_func = norm.cdf
        ppf_func = norm.ppf
    elif dist_name == "Log-Normal":
        ref_samples = lognorm.rvs(s=0.954, scale=np.exp(0), size=n)  # mu=0, sigma=0.954
        cdf_func = lambda x: lognorm.cdf(x, s=0.954, scale=np.exp(0))
        ppf_func = lambda u: lognorm.ppf(u, s=0.954, scale=np.exp(0))

    # Generar Monte Carlo con U
    sim_vals = ppf_func(U)

    # Gráficos lado a lado
    col1, col2 = st.columns(2)

    with col1:
        fig_ref = go.Figure()
        fig_ref.add_trace(go.Histogram(x=ref_samples, nbinsx=50, histnorm='probability density', name="Referencia", opacity=0.6,marker=dict(color='green')))
        fig_ref.add_trace(go.Histogram(x=sim_vals, nbinsx=50, histnorm='probability density', name="Simulado",marker=dict(color='red'), opacity=0.6))
        fig_ref.update_layout(title="📊 Histograma: Ref vs Sim", barmode='overlay', height=400)
        st.plotly_chart(fig_ref, use_container_width=True)

    with col2:
        
        x_ref, y_ref = ecdf(ref_samples)
        x_sim, y_sim = ecdf(sim_vals)
        x_vals = np.linspace(min(sim_vals.min(), ref_samples.min()), max(sim_vals.max(), ref_samples.max()), 300) 
        fig_cdf = go.Figure()
        fig_cdf.add_trace(go.Scatter(x=x_vals, y=cdf_func(x_vals), name="CDF teórica", line=dict(color='black')))
        fig_cdf.add_trace(go.Scatter(x=x_ref, y=y_ref, name="CDF Ref", line=dict(color='green')))
        fig_cdf.add_trace(go.Scatter(x=x_sim, y=y_sim, name="CDF Simulada", line=dict(color='red')))
        fig_cdf.update_layout(title="📈 Función de distribución acumulada", height=400)
        st.plotly_chart(fig_cdf, use_container_width=True)
        
        

    # Estadísticas
    st.markdown("### 📌 Estadísticas de referencia vs simulación")
    def stat_table(ref, sim):
            import pandas as pd
            stats = {
            "Media": [np.mean(ref), np.mean(sim)],
            "Desviación": [np.std(ref), np.std(sim)],
            "Mínimo": [np.min(ref), np.min(sim)],
            "Máximo": [np.max(ref), np.max(sim)],
            }
            df = pd.DataFrame(stats, index=["Referencia", "Simulación"]).T
            return df.round(3)

    df_stats = stat_table(ref_samples, sim_vals)
    st.table(df_stats)
