import dash
from dash import dcc, html, dash_table, Input, Output
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# Cargar datos
df = pd.read_excel("Yacimientos_2daRegion_CruceFinal.xlsx")

# Opciones disponibles para seleccionar categoría
# Se excluyen columnas que no son útiles para categorizar o que son IDs
columnas_para_categoria = [col for col in df.columns if col not in ['ID', 'UTM ESTE (METROS)', 'UTM Norte (METROS)', 'LAT', 'LON', 'Coincidencia_KML']]
categorias_disponibles = [{"label": col, "value": col} for col in columnas_para_categoria]

# Inicializar app
app = dash.Dash(__name__)
app.title = "Mapa con Capas Metalogenéticas ON/OFF"

app.layout = html.Div([
    html.H2("Mapa de Yacimientos de la 2da Región de Chile con Diferenciación Metalogenética"),
    
    html.Label("Selecciona categoría para agrupar:"),
    dcc.Dropdown(
        id="categoria-dropdown",
        options=categorias_disponibles,
        value="RECURSO",  # Valor inicial por defecto, puedes cambiarlo
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
    # Asegurarse de que las columnas 'LAT' y 'LON' sean numéricas y manejar valores nulos si los hay
    df_cleaned = df.dropna(subset=['LAT', 'LON'])

    fig = px.scatter_mapbox(
        df_cleaned, # Usar df_cleaned para evitar errores con valores nulos
        lat="LAT",
        lon="LON",
        hover_name="Depósito",
        hover_data=["RECURSO", "ESTADO", "TIPO DE RECURSO"], # Columnas disponibles en tu nuevo archivo
        color=categoria,
        title=f"Yacimientos por {categoria}"
    )

    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox=dict(
            center=dict(lat=-24.5, lon=-69.5),  # Centrado aproximado de la 2da Región de Chile (Antofagasta)
            zoom=6  # Nivel de zoom ajustado para ver la región en más detalle
        ),
        margin={"r": 0, "t": 30, "l": 0, "b": 0},
        legend_title_text=categoria
    )

    conteo = df_cleaned[categoria].value_counts().reset_index()
    conteo.columns = [categoria, "Cantidad"]
    fig_barras = px.bar(
        conteo,
        x=categoria,
        y="Cantidad",
        title=f"Distribución de Yacimientos por {categoria}"
    )
    fig_barras.update_layout(xaxis_title=categoria, yaxis_title="Cantidad")

    return fig, fig_barras

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8506))  # Usa 8050 por defecto si no hay PORT
    app.run(debug=False, port=port, host='0.0.0.0')
