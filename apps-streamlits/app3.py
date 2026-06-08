# streamlit_app_i90.py
import streamlit as st
import numpy as np
import plotly.graph_objects as go
import base64
from pathlib import Path

st.set_page_config(layout="centered")

# ---------- Mostrar avatar en el sidebar ----------
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

st.title("📊 Efecto Volumen-Varianza en la Métrica I90 según correlación mensual ")

st.markdown("Esta app permite visualizar cómo la incertidumbre relativa (I90) evoluciona al pasar de un análisis mensual a trimestral o anual, bajo diferentes niveles de correlación temporal entre meses.")

st.latex(r"\text{I90}_{\text{periodo}} = \text{I90}_{\text{mensual}} \cdot \sqrt{ \frac{1 + (n - 1)\rho}{n} }")

st.markdown("Donde:  ")
st.latex(r"n = \text{número de periodos agrupados (3 = trimestre, 12 = año)}")
st.latex(r"\rho = \text{correlación entre meses}")

# --- Entradas del usuario ---
i90_mensual = st.number_input("I90 mensual relativo (%)", value=10.0, step=0.1)

rhos = np.linspace(0, 1, 100)
i90_trimestral = i90_mensual * np.sqrt((1 + 2 * rhos) / 3)
i90_anual = i90_mensual * np.sqrt((1 + 11 * rhos) / 12)

fig = go.Figure()
fig.add_trace(go.Scatter(x=rhos, y=i90_trimestral, mode='lines', name='I90 Trimestral'))
fig.add_trace(go.Scatter(x=rhos, y=i90_anual, mode='lines', name='I90 Anual'))
fig.add_trace(go.Scatter(x=rhos, y=[i90_mensual]*len(rhos), mode='lines', name='I90 Mensual', line=dict(dash='dash')))

fig.update_layout(
    title="I90 en función de la correlación entre meses",
    xaxis_title="Correlación spacial-temporal entre meses (ρ)",
    yaxis_title="I90 (%)",
    height=500
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("""
### Interpretación:
- Si los meses son **independientes** (ρ = 0), la incertidumbre disminuye notablemente al agrupar.
- Si hay **alta correlación** (ρ → 1), la incertidumbre **no disminuye** significativamente.
- Esta métrica es útil para evaluar la disminución de incertidumbre al aumentar el volumen de producción o N periodos.
""")

st.markdown("""
### Hipótesis:
- Se asumen que los meses tienen todos la misma desviación estándar
- Se asume que la correlación es constante entre todos los meses.
- Se asume que el valor esperado es similar entre meses
- Se asume que la distribuciones de la incertidumbre mensual son cercanas a gaussianas
""")

st.markdown("""
### Pregunta:
- Que pasaría con este tema entre Rosario y Rosario Oeste?
- Es tan mala la incertidumbre como parece de ROSW?
- Pensar en Oro - Oregénico LOM de 5 años por 150 años produciendo....
""")
