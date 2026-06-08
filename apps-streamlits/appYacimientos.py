import dash
from dash import dcc, html, dash_table, Input, Output
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# Cargar datos
df = pd.read_excel("depositos_australianos_completos_215_actualizado.xlsx")

# Opciones disponibles para seleccionar categoría
categorias_disponibles = df.columns

# Inicializar app
app = dash.Dash(__name__)
app.title = "Mapa con Capas Metalogenéticas ON/OFF"

app.layout = html.Div([
    html.H2("Mapa de Yacimientos Australianos con Diferenciación Metalogenética"),
    
    html.Label("Selecciona categoría para agrupar:"),
    dcc.Dropdown(
        id="categoria-dropdown",
        options=[{"label": cat, "value": cat} for cat in categorias_disponibles],
        value="Mena principal",
        clearable=False
    ),

    dcc.Graph(id="mapa-yacimientos"),
    dcc.Graph(id="grafico-barras"),

    html.H4("Tabla de Yacimientos"),
    dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in df.columns],
        data=df.to_dict("records"),
        page_size=10,
        filter_action="native",
        sort_action="native",
        export_format="xlsx",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left"}
    )
])

@app.callback(
    Output("mapa-yacimientos", "figure"),
    Output("grafico-barras", "figure"),
    Input("categoria-dropdown", "value")
)
def actualizar_figuras(categoria):
    fig = px.scatter_mapbox(
        df,
        lat="Lat", lon="Lon",
        hover_name="Depósito",
        hover_data=["Modelo", "Edad (Ma)", "Tonalaje (Mt)", "Región"],
        color=categoria,
        title=f"Yacimientos por {categoria}"
    )

    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox=dict(
            center=dict(lat=-25, lon=120),  # Centrado aproximado de Australia
            zoom=2  # Zoom más alejado (cuanto menor el número, más alejado)
        ),
        margin={"r": 0, "t": 30, "l": 0, "b": 0},
        legend_title_text=categoria
    )

    conteo = df[categoria].value_counts().reset_index()
    conteo.columns = [categoria, "Cantidad"]
    fig_barras = px.bar(
        conteo,
        x=categoria, y="Cantidad",
        title=f"Distribución de Yacimientos por {categoria}"
    )

    return fig, fig_barras

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8505))  # Usa 8050 por defecto si no hay PORT
    app.run(debug=False, port=port, host='0.0.0.0')
