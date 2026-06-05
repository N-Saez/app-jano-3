"""
app.py
------
Aplicación Streamlit docente: interpretación geológica, estimación,
categorización y análisis de incertidumbre en 2D.

Ejecución:
    streamlit run app.py

Flujo guiado del estudiante (etapas que se liberan en orden):
  1. dibujar 5 escenarios -> botón «Siguiente»
  2. estimar (kriging OK por dominios)  -> pasa a Resultados
  3. categorizar (zonas Verde/Amarillo/Rojo en Resultados)
  4. p(mineral) y p(1-p) -> pasa a Incertidumbre
  5. develar realidad.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import geometry
import plotting
import professor
import reporting
import state
import uncertainty
from classification import classify_resources
from estimation import estimate_scenario, get_scenario_weights_for_block

# ------------------------------------------------------------------
# Shim de compatibilidad: streamlit-drawable-canvas 0.9.3 usa
# st_image.image_to_url, que Streamlit >= 1.41 movió a
# streamlit.elements.lib.image_utils (misma firma posicional).
# ------------------------------------------------------------------
try:
    import streamlit.elements.image as _st_image
    if not hasattr(_st_image, "image_to_url"):
        from streamlit.elements.lib.image_utils import image_to_url \
            as _image_to_url
        _st_image.image_to_url = _image_to_url
except Exception:
    pass

# El canvas de dibujo es una dependencia externa: si falta, la app sigue
# funcionando (sin dibujo) y muestra cómo instalarla.
try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS = True
except ImportError:
    HAS_CANVAS = False

CANVAS_PX = 800   # tamaño del canvas en píxeles (igual al mapa principal)

st.set_page_config(page_title="Interpretación y recursos 2D — DIMIN USACH",
                   layout="wide", page_icon="⛏️")

# ------------------------------------------------------------------
# Identidad corporativa (Depto. de Ingeniería en Minas, USACH)
# Colores del logo de la plantilla PPTX:
#   naranjo #EE7700 | gris azulado #37404A | turquesa #00A79A
# ------------------------------------------------------------------
USACH_NARANJO = "#EE7700"
USACH_GRIS = "#37404A"
USACH_TURQUESA = "#00A79A"
LOGO_PATH = Path(__file__).parent / "assets" / "logo_dimin_usach.png"
if LOGO_PATH.exists():
    st.logo(str(LOGO_PATH), size="large")

# Acentos visuales: títulos en gris corporativo, etapas con borde
# naranjo y línea turquesa bajo el encabezado principal
st.markdown(f"""
<style>
h1, h2, h3 {{ color: {USACH_GRIS}; }}
h2 {{ border-bottom: 3px solid {USACH_TURQUESA}; padding-bottom: 4px; }}
[data-testid="stSidebar"] h4 {{
    color: {USACH_GRIS};
    border-left: 4px solid {USACH_NARANJO};
    padding-left: 8px;
}}
[data-testid="stSidebar"] hr {{ margin: 8px 0; }}
</style>
""", unsafe_allow_html=True)

state.init_state()
ss = st.session_state
D = state.DEFAULTS

# Supuestos FIJOS del caso (sin controles en la interfaz)
cutoff = D["cutoff"]        # 0.30 %Cu
espesor = D["espesor"]      # 20 m
densidad = D["densidad"]    # 2.6 t/m³
ton_b = reporting.block_tonnage(ss.case["block_size"], espesor, densidad)


# ==================================================================
# CALLBACKS DEL FLUJO GUIADO
# Se ejecutan ANTES de renderizar la página, por lo que los bloqueos
# de etapa quedan actualizados en el mismo run (sin st.rerun()).
# ==================================================================
FIXED_VARIOGRAM = {"azimuth": D["azimuth"], "r_major": D["r_major"],
                   "r_minor": D["r_minor"], "nugget": 0.0,
                   "sill": D["sill"], "model": D["vmodel"]}


def cb_siguiente():
    """Etapa 1 -> 2: libera la sección de Estimación."""
    ss.stage_est_unlocked = True


def cb_estimar():
    """Estima TODOS los escenarios por dominios y pasa a Resultados."""
    if not ss.scenarios:
        return
    c = ss.case
    for sc in ss.scenarios:
        sc["est_result"] = estimate_scenario(
            "Kriging ordinario", c["samples"], c["blocks"],
            sc["mask"], sc["sample_mask"], FIXED_VARIOGRAM)
        sc["estimated"] = True
    ss.pending_view = "📋 Resultados"


def cb_categorizar():
    """Marca la categorización, libera Incertidumbre, va a Resultados."""
    if not any(sc.get("est_result") for sc in ss.scenarios):
        return
    for sc in ss.scenarios:
        sc["classified"] = True
    ss.categorized = True
    ss.pending_view = "📋 Resultados"


def cb_gen_p():
    """Computa p(mineral) desde los escenarios y va a Incertidumbre."""
    if not ss.scenarios:
        return
    ss.p_mineral = uncertainty.compute_p_mineral(
        ss.scenarios, len(ss.case["blocks"]))
    ss.pending_view = "🎲 Incertidumbre"


def cb_demo():
    """MODO PROFESOR: reemplaza los escenarios por 5 interpretaciones
    generadas automáticamente (sólo para probar la aplicación)."""
    c = ss.case
    sets = professor.generate_demo_interpretations(c, cutoff)
    ss.scenarios = []
    for i, polys in enumerate(sets, start=1):
        mask, area = geometry.scenario_mask(polys, c["blocks"])
        smask = geometry.samples_inside(polys, c["samples"])
        ss.scenarios.append(state.new_scenario_dict(
            i, f"Escenario {i}", polys, mask, smask, area,
            c["block_size"], espesor, densidad))
    # Reiniciar el flujo guiado con los escenarios nuevos
    ss.active_scenario = 1
    ss.pending_active = 1
    ss.p_mineral = None
    ss.categorized = False
    ss.stage_est_unlocked = False
    ss.pending_view = "✏️ Dibujo"


# ==================================================================
# PANEL IZQUIERDO: CONTROLES
# ==================================================================
with st.sidebar:
    # Logo institucional en la cabecera del panel
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), use_container_width=True)
    st.title("⛏️ Controles")

    # (Sin controles de caso sintético: el caso es fijo —
    #  cutoff 0.30 %Cu, espesor 20 m, densidad 2.6 t/m³, 20 800 t/bloque)

    # ---------- Controles del mapa ----------
    with st.expander("🗺️ Controles del mapa", expanded=False):
        layer_opt = st.radio("Capa a mostrar en el mapa", [
            "Ninguna", "Ley estimada", "Categorías de recurso",
            "p(mineral)", "p(1-p)", "Distancia a sondajes"],
            index=0)
        show_labels = st.checkbox("Mostrar valores de ley (Cu%)", True)
        show_grid = st.checkbox("Mostrar grilla de bloques", False)
        show_saved = st.checkbox("Mostrar escenarios guardados", False)
        # Control opcional: zonas Medido/Indicado/Inferido sobre el mapa
        show_cat_zones = st.checkbox(
            "Mostrar zonas Medido/Indicado/Inferido",
            value=False, disabled=not ss.categorized,
            help="Se habilita después de categorizar recursos.")
        point_size = st.slider("Tamaño de puntos", 15, 100, 45, 5)

    # ==================================================================
    # ETAPAS DEL EJERCICIO (siempre visibles, se activan en orden)
    # ==================================================================
    st.divider()
    st.markdown("#### Etapa 1 · Interpretación")
    n_esc = len(ss.scenarios)
    meta = D["meta_escenarios"]
    st.progress(min(n_esc / meta, 1.0),
                text=f"Escenarios guardados: {n_esc} / {meta}")

    # Sólo se interpretan polígonos MINERALIZADOS (envolvente)
    draw_mode = st.radio("Herramienta",
                         ["Interpretar polígono", "Mover / editar"],
                         horizontal=True)

    # Nombres FIJOS: Escenario 1..5. Al guardar se ocupa el primer
    # espacio libre; para reinterpretar uno hay que borrarlo primero.
    usados = {sc["scenario_id"] for sc in ss.scenarios}
    libres = [i for i in range(1, meta + 1) if i not in usados]
    if libres:
        st.caption(f"El próximo guardado será **Escenario {libres[0]}**.")
    else:
        st.caption(f"Los {meta} escenarios están completos "
                   f"(borre uno para reinterpretarlo).")

    guardar = st.button("💾 Guardar interpretación como escenario",
                        use_container_width=True, type="primary")
    nuevo = st.button("➕ Nuevo escenario (limpiar lienzo)",
                      use_container_width=True)

    # Escenario activo con flechas −/+ (antes / después). Tras guardar,
    # salta al recién creado vía pending_active (los widgets no toman
    # nuevos valores por defecto después de creados).
    if "active_sel" not in ss:
        ss.active_sel = 1
    if ss.get("pending_active"):
        ss.active_sel = ss.pending_active
        ss.pending_active = None
    sel = st.number_input("Escenario activo", 1, meta, step=1,
                          key="active_sel")
    ss.active_scenario = int(sel)
    if state.get_scenario(ss.active_scenario) is None:
        st.caption(f"⚠️ El Escenario {ss.active_scenario} aún no está "
                   f"guardado.")
    if st.button("🗑️ Borrar escenario activo", use_container_width=True,
                 disabled=state.get_scenario(ss.active_scenario) is None):
        state.delete_scenario(ss.active_scenario)
        st.rerun()

    # Al completar los 5 escenarios aparece «Siguiente» -> libera Etapa 2
    if n_esc >= meta and not ss.stage_est_unlocked:
        st.button("➡️ Siguiente: liberar Estimación",
                  use_container_width=True, type="primary",
                  key="btn_siguiente", on_click=cb_siguiente)

    # ---------- Etapa 2: Estimación (sólo el botón) ----------
    st.divider()
    st.markdown("#### Etapa 2 · Estimación")
    st.button("⚙️ Estimar leyes", use_container_width=True,
              type="primary", key="btn_estimar", on_click=cb_estimar,
              disabled=(not ss.stage_est_unlocked or not ss.scenarios))
    any_estimated = any(sc.get("est_result") for sc in ss.scenarios)

    # ---------- Etapa 3: Categorización ----------
    st.divider()
    st.markdown("#### Etapa 3 · Categorización")
    with st.expander("Distancias de categorización (m)", expanded=False):
        d_med = st.number_input("Distancia Medido (m)", 10.0, 500.0,
                                D["d_med"], 10.0,
                                disabled=not any_estimated)
        d_ind = st.number_input("Distancia Indicado (m)", 10.0, 500.0,
                                D["d_ind"], 10.0,
                                disabled=not any_estimated)
        d_inf = st.number_input("Distancia Inferido (m)", 10.0, 500.0,
                                D["d_inf"], 10.0,
                                disabled=not any_estimated)
    st.button("🏷️ Categorizar recursos",
              use_container_width=True, type="primary",
              key="btn_categorizar", on_click=cb_categorizar,
              disabled=not any_estimated)

    # ---------- Etapa 4: Incertidumbre (sólo el botón) ----------
    st.divider()
    st.markdown("#### Etapa 4 · Incertidumbre de escenarios")
    st.button("🎲 Generar probabilidad de mineralización",
              use_container_width=True, type="primary",
              key="btn_genp", on_click=cb_gen_p,
              disabled=not ss.categorized)

    # ---------- Etapa final: Realidad oculta ----------
    st.divider()
    st.markdown("#### Etapa final · Realidad oculta")
    st.warning("⚠️ Use esta opción **sólo al final** del ejercicio.")
    confirmo = st.checkbox(f"Confirmo que terminé la actividad "
                           f"({D['meta_escenarios']} escenarios)",
                           disabled=ss.p_mineral is None)
    if st.button("🔓 Develar realidad", use_container_width=True,
                 disabled=not confirmo):
        ss.revealed = True
    if ss.revealed:
        st.success("La realidad está develada (sección «Realidad»).")

    # ---------- Modo profesor ----------
    # TEMPORAL: visible siempre mientras se prueba la app.
    # Para volver a ocultarlo (sólo con ?profesor=1 en la URL), usar:
    #   if st.query_params.get("profesor") in ("1", "true"):
    if True:
        with st.expander("🧑‍🏫 Modo profesor", expanded=False):
            st.caption("Sólo para probar la aplicación: genera 5 "
                       "interpretaciones automáticas (reemplaza las "
                       "existentes) construidas desde los sondajes "
                       "mineralizados.")
            st.button("⚡ Generar 5 interpretaciones de prueba",
                      use_container_width=True, key="btn_demo",
                      on_click=cb_demo)

# (Las acciones de Estimar / Categorizar / Generar p se ejecutan en los
#  callbacks cb_estimar / cb_categorizar / cb_gen_p, ANTES del render)
case = ss.case
blocks = case["blocks"]
samples = case["samples"]
n_blocks = len(blocks)

# Productos derivados vigentes
p = ss.p_mineral
p1p = uncertainty.compute_p_one_minus_p(p) if p is not None else None
active_sc = state.get_scenario(ss.active_scenario)
active_cat = None
active_est = None   # estimación PROPIA del escenario activo
if active_sc is not None:
    active_cat = classify_resources(case["dist"], active_sc["mask"],
                                    d_med, d_ind, d_inf)
    active_est = active_sc.get("est_result")

LAYER_MAP = {"Ninguna": None, "Ley estimada": "estimada",
             "Categorías de recurso": "categorias", "p(mineral)": "p",
             "p(1-p)": "p1p", "Distancia a sondajes": "dist"}
layer = LAYER_MAP[layer_opt]


# ==================================================================
# PANEL CENTRAL: VISTAS NAVEGABLES
# (radio horizontal en vez de st.tabs para poder navegar
#  programáticamente: estimar -> Resultados, p(mineral) -> Incertidumbre)
# ==================================================================
VIEWS = ["✏️ Dibujo", "🗺️ Mapa", "📋 Resultados", "📊 Comparación",
         "🎲 Incertidumbre", "🔓 Realidad", "💾 Exportar"]
if "view" not in ss:
    ss.view = VIEWS[0]
if ss.get("pending_view"):
    ss.view = ss.pending_view     # navegación programática
    ss.pending_view = None
view = st.radio("Sección", VIEWS, horizontal=True, key="view",
                label_visibility="collapsed")
st.divider()


# ------------------------------------------------------------------
# VISTA 1: dibujo de interpretaciones
# ------------------------------------------------------------------
if view == "✏️ Dibujo":
    # (1) Título de la etapa, arriba
    st.markdown("## 🧭 Interpretación")
    st.markdown(
        "**Interprete** la envolvente mineralizada: haga clic para "
        "agregar vértices y **clic derecho para cerrar** el polígono. "
        "Se puede interpretar **más de un polígono** por escenario. "
        "Pista regional: orientación dominante ≈ **37°**.")

    canvas = None
    if not HAS_CANVAS:
        st.error("Falta el componente de dibujo. Instale con:\n\n"
                 "`pip install streamlit-drawable-canvas`")
    else:
        # (2) Mapa de interpretación EXCLUSIVO para interpretar:
        # sólo sondajes (+ grilla opcional). Sin capas, sin escenarios
        # previos y sin la realidad aunque esté develada.
        bg = plotting.render_canvas_background(
            case, cutoff, scenario_polys=None, layer=None,
            est=None, p=None, show_labels=show_labels,
            show_grid=show_grid, show_truth=False,
            size_px=CANVAS_PX)

        # Todos los polígonos interpretados son mineralizados (rojos)
        cc = st.columns([1, 12, 1])[1]   # canvas centrado
        with cc:
            canvas = st_canvas(
                background_image=bg,
                drawing_mode=("polygon"
                              if draw_mode == "Interpretar polígono"
                              else "transform"),
                stroke_color="#FF0000", fill_color="rgba(255,0,0,0.20)",
                stroke_width=2,
                height=CANVAS_PX, width=CANVAS_PX,
                update_streamlit=True,
                key=f"canvas_{ss.canvas_version}",
            )

    # ---- Estado del lienzo y validación ----
    poligonos = []
    if HAS_CANVAS and canvas is not None and canvas.json_data:
        poligonos = geometry.parse_canvas_polygons(
            canvas.json_data, CANVAS_PX, case["domain"])
    validos = [q for q in poligonos
               if geometry.validate_polygon(q["coords"]) is not None]
    cmid = st.columns([1, 3, 1])[1]
    with cmid:
        st.caption(f"Polígonos interpretados en el lienzo: "
                   f"**{len(validos)}**")
        if len(validos) < len(poligonos):
            st.warning(f"{len(poligonos) - len(validos)} polígono(s) "
                       f"inválido(s) o demasiado pequeño(s): se ignorarán.")

    if guardar:
        vmin = [q for q in validos if q["tipo"] == "mineral"]
        if not vmin:
            st.error("Interprete al menos un polígono cerrado antes "
                     "de guardar.")
        elif not libres:
            st.error(f"Ya tiene los {meta} escenarios guardados. "
                     f"Borre uno para reemplazarlo.")
        else:
            mask, area_poly = geometry.scenario_mask(validos, blocks)
            # Muestras dentro de la interpretación: definen el dominio
            # de estimación "dentro" de este escenario
            smask = geometry.samples_inside(validos, samples)
            if smask.sum() == 0:
                st.warning("Ojo: la interpretación no encierra ningún "
                           "sondaje — el dominio interior no podrá "
                           "estimarse.")
            # Ocupa el primer espacio libre (nombre fijo Escenario N)
            slot = libres[0]
            sc = state.new_scenario_dict(
                slot, f"Escenario {slot}", validos, mask, smask,
                area_poly, case["block_size"], espesor, densidad)
            ss.scenarios.append(sc)
            ss.scenarios.sort(key=lambda s: s["scenario_id"])
            ss.active_scenario = slot
            ss.pending_active = slot  # mover el slider a este escenario
            ss.p_mineral = None       # la probabilidad queda obsoleta
            ss.canvas_version += 1    # limpiar lienzo para el siguiente
            st.rerun()

    if nuevo:
        ss.canvas_version += 1
        st.rerun()

    # ---- Tabla de escenarios guardados (centrada, simplificada) ----
    if ss.scenarios:
        cu_v = samples["Cu_pct"].to_numpy()
        resumen = pd.DataFrame([{
            "Escenario": sc["name"],
            "Polígonos": len(sc["polygons"]),
            "Tonelaje (Mt)": int(sc["mask"].sum()) * ton_b / 1e6,
            "Sondajes dentro": int(sc["sample_mask"].sum()),
            "Mineralizados": int((cu_v[sc["sample_mask"]] >= cutoff).sum()),
            "Estériles": int((cu_v[sc["sample_mask"]] < cutoff).sum()),
        } for sc in ss.scenarios])
        ctab = st.columns([1, 3, 1])[1]
        with ctab:
            st.markdown("#### Escenarios guardados")
            st.dataframe(
                resumen.style.format({"Tonelaje (Mt)": "{:.2f}"}),
                hide_index=True, use_container_width=True)


# ------------------------------------------------------------------
# VISTA 2: mapa principal con capas
# ------------------------------------------------------------------
if view == "🗺️ Mapa":
    faltantes = {"estimada": active_est is None,
                 "categorias": active_cat is None or active_est is None,
                 "p": p is None, "p1p": p1p is None}
    if layer and faltantes.get(layer, False):
        st.info("Esa capa aún no está disponible: genere primero la "
                "estimación / categorización / probabilidad según "
                "corresponda (botones del panel izquierdo).")
    if layer == "estimada" and active_est is not None and active_sc:
        st.caption(f"Ley estimada del escenario activo "
                   f"**{active_sc['name']}** (dominios dentro/fuera de su "
                   f"interpretación). Cambie el escenario activo para ver "
                   f"cómo cambia la estimación.")
    fig = plotting.make_main_map(
        case, cutoff, layer=layer, layer_name=layer_opt,
        est=active_est, categories=active_cat, p=p, p1p=p1p,
        cat_overlay=(active_cat if (show_cat_zones and ss.categorized)
                     else None),
        scenario_polys=(active_sc["polygons"] if active_sc else None),
        other_scenarios=(ss.scenarios if show_saved else None),
        show_samples=True, show_labels=show_labels, show_grid=show_grid,
        show_truth=ss.revealed, point_size=point_size,
        title=f"Dominio 1000 × 1000 m — capa: {layer_opt}")
    st.pyplot(fig, use_container_width=False)

    with st.expander("📄 Tabla de sondajes"):
        tabla_s = samples.copy()
        tabla_s["clase"] = np.where(tabla_s["Cu_pct"] >= cutoff,
                                    "mineralizado", "estéril")
        st.dataframe(tabla_s.round(3), hide_index=True,
                     use_container_width=True)


# ------------------------------------------------------------------
# VISTA 3: resultados del escenario activo + pesos de kriging
# ------------------------------------------------------------------
if view == "📋 Resultados":
    if active_sc is None:
        st.info("Guarde un escenario para ver sus resultados.")
    elif active_est is None:
        st.info("Presione «⚙️ Estimar leyes» en el panel izquierdo "
                "(la estimación es propia de cada escenario).")
    else:
        est = active_est
        mask = active_sc["mask"]
        st.subheader(f"Reporte de recursos — {active_sc['name']}")
        n_in = int(active_sc["sample_mask"].sum())
        n_out = len(samples) - n_in
        st.caption(f"Estimación por dominios de este escenario: bloques "
                   f"dentro de la interpretación estimados con las "
                   f"**{n_in}** muestras interiores; bloques de afuera con "
                   f"las **{n_out}** restantes ({est['method']}).")
        if np.isnan(est["est"][mask]).any():
            st.warning("Hay bloques interiores sin estimar (la "
                       "interpretación no encierra sondajes suficientes).")
        rep = reporting.report_resources_by_category(
            active_sc["name"], mask, active_cat, est["est"],
            case["block_size"], espesor, densidad)
        # Actualizar los campos de resultados del escenario (sección 4)
        tot = rep[rep["Categoría"] == "Total recurso"].iloc[0]
        active_sc.update(toneladas=float(tot["Toneladas"]),
                         ley_media=(None if pd.isna(tot["Ley media Cu%"])
                                    else float(tot["Ley media Cu%"])),
                         metal_contenido=float(tot["Metal Cu (t)"]),
                         resource_table=rep)
        st.dataframe(
            rep.style.format({"Área m²": "{:,.0f}", "Toneladas": "{:,.0f}",
                              "Ley media Cu%": "{:.3f}",
                              "Metal Cu (t)": "{:,.0f}",
                              "Ley mín": "{:.3f}", "Ley máx": "{:.3f}"}),
            hide_index=True, use_container_width=True)
        st.caption(f"Supuestos: bloque {case['block_size']:.0f} m, espesor "
                   f"{espesor:.0f} m, densidad {densidad} t/m³ → "
                   f"{ton_b:,.0f} t/bloque. El reporte sólo cuenta los "
                   f"bloques dentro de la interpretación mineralizada.")

        # Zonas de categorización semi-transparentes (tras Categorizar)
        if ss.categorized and active_cat is not None:
            st.subheader("Zonas de categorización")
            st.pyplot(plotting.make_main_map(
                case, cutoff, cat_overlay=active_cat,
                scenario_polys=active_sc["polygons"],
                show_labels=False, point_size=20,
                title=("Medido (verde) / Indicado (amarillo) / "
                       "Inferido (rojo)"),
                figsize=(6.8, 5.8)), use_container_width=False)
            st.caption("También puede sobreponerlas en cualquier mapa con "
                       "el control «Mostrar zonas Medido/Indicado/"
                       "Inferido» del panel izquierdo.")

        # Zona de incertidumbre geológica (tras computar p(mineral))
        if p1p is not None:
            st.subheader("Zona de incertidumbre geológica")
            st.pyplot(plotting.make_main_map(
                case, cutoff, layer="p1p", p1p=p1p, show_labels=False,
                point_size=20,
                title="p(1-p) — máxima donde los escenarios discrepan",
                figsize=(6.8, 5.8)), use_container_width=False)

    # ---- Inspector de pesos de kriging (del escenario activo) ----
    # Los controles viven aquí (no en el panel de etapas) para que la
    # Etapa 2 tenga sólo el botón de estimar.
    if active_est is not None:
        st.divider()
        show_weights = st.checkbox("🔍 Mostrar pesos de kriging", False)
    else:
        show_weights = False
    if show_weights:
        cxy = st.columns([1, 1, 2])
        wx = cxy[0].number_input("X del bloque (m)", 10.0, 990.0,
                                 510.0, 20.0)
        wy = cxy[1].number_input("Y del bloque (m)", 10.0, 990.0,
                                 510.0, 20.0)
        st.subheader("🔍 Pesos de kriging del bloque seleccionado")
        # Bloque más cercano a las coordenadas pedidas
        bid = int(np.argmin((blocks["x"] - wx) ** 2 + (blocks["y"] - wy) ** 2))
        info = get_scenario_weights_for_block(bid, samples, blocks,
                                              active_est)
        if info is None or info["samples_used"].empty:
            st.warning("Ese bloque pertenece a un dominio sin muestras: "
                       "no hay pesos que mostrar.")
        else:
            c1, c2 = st.columns([3, 2])
            with c1:
                st.pyplot(plotting.make_kriging_weights_map(case, cutoff,
                                                            info),
                          use_container_width=False)
            with c2:
                st.markdown(
                    f"**Bloque** ({info['x']:.0f}, {info['y']:.0f}) — "
                    f"dominio **{info['domain']}** de "
                    f"{active_sc['name']} — ley estimada "
                    f"**{info['estimated_grade']:.3f} %Cu**")
                st.dataframe(info["samples_used"].head(15), hide_index=True,
                             use_container_width=True)
                st.caption("Sólo participan las muestras del MISMO dominio "
                           "que el bloque (frontera dura): la "
                           "interpretación controla qué datos se usan, "
                           "además de qué bloques se reportan.")


# ------------------------------------------------------------------
# VISTA 4: comparación entre escenarios
# ------------------------------------------------------------------
if view == "📊 Comparación":
    estimados = [sc for sc in ss.scenarios if sc.get("est_result")]
    if len(ss.scenarios) == 0:
        st.info(f"Guarde escenarios para compararlos "
                f"(meta: {D['meta_escenarios']}).")
    elif not estimados:
        st.info("Presione «⚙️ Estimar leyes» para poder comparar.")
    else:
        if len(estimados) < len(ss.scenarios):
            st.warning(f"{len(ss.scenarios) - len(estimados)} escenario(s) "
                       f"aún sin estimar: presione «Estimar leyes» para "
                       f"incluirlos.")
        totals = reporting.report_total_by_scenario(
            estimados, case["dist"], d_med, d_ind, d_inf,
            case["block_size"], espesor, densidad)
        st.subheader("Resumen por escenario (cada uno con su estimación)")
        st.dataframe(
            totals.style.format({"Área m²": "{:,.0f}",
                                 "Toneladas": "{:,.0f}",
                                 "Ley media Cu%": "{:.3f}",
                                 "Metal Cu (t)": "{:,.0f}",
                                 "% Medido": "{:.1f}", "% Indicado": "{:.1f}",
                                 "% Inferido": "{:.1f}",
                                 "% No clasificado": "{:.1f}"}),
            hide_index=True, use_container_width=True)

        perc = reporting.scenario_percentiles(totals)
        st.subheader("Estadísticas entre escenarios (P5 / P50 / P95 / I90)")
        st.dataframe(
            perc.style.format({"P5": "{:,.1f}", "P50": "{:,.1f}",
                               "P95": "{:,.1f}", "I90 abs": "{:,.1f}",
                               "I90 rel %": "{:.1f}"}),
            hide_index=True, use_container_width=True)

        st.pyplot(plotting.make_scenario_stripplots(totals),
                  use_container_width=False)

        st.subheader("💬 Comentarios automáticos")
        for c in reporting.auto_comments(perc, totals,
                                         meta=D["meta_escenarios"]):
            st.markdown(f"- {c}")


# ------------------------------------------------------------------
# VISTA 5: incertidumbre geológica
# ------------------------------------------------------------------
if view == "🎲 Incertidumbre":
    if p is None:
        st.info("Presione «🎲 Generar probabilidad de mineralización» en el "
                "panel izquierdo (requiere escenarios guardados).")
    else:
        n_used = len(ss.scenarios)
        st.markdown(f"Probabilidad calculada con **{n_used} escenario(s)**: "
                    f"`p = n° escenarios que incluyen el bloque / {n_used}`")
        c1, c2 = st.columns(2)
        with c1:
            st.pyplot(plotting.make_main_map(
                case, cutoff, layer="p", p=p, show_labels=False,
                point_size=18, title="p(mineral)",
                figsize=(6.4, 5.6)), use_container_width=False)
        with c2:
            st.pyplot(plotting.make_main_map(
                case, cutoff, layer="p1p", p1p=p1p, show_labels=False,
                point_size=18, title="Incertidumbre geológica p(1-p)",
                figsize=(6.4, 5.6)), use_container_width=False)

        st.subheader("Comparación: distancia a sondajes vs p(1-p)")
        st.pyplot(plotting.make_dist_vs_p1p(case, p1p),
                  use_container_width=True)
        st.markdown(
            "> **Discusión:** una zona cercana a sondajes puede tener "
            "alta incertidumbre geológica si la continuidad del cuerpo es "
            "ambigua; una zona lejana puede ser poco incierta si todos los "
            "escenarios coinciden en su interpretación.")


# ------------------------------------------------------------------
# VISTA 6: realidad develada
# ------------------------------------------------------------------
if view == "🔓 Realidad":
    if not ss.revealed:
        st.info("🔒 La realidad está oculta. Devélela al FINAL del ejercicio "
                "desde el panel izquierdo (sección 6).")
    else:
        # --------------------------------------------------------------
        # Comparación 2x2: interpretación vs realidad (escenario activo)
        #   [interpretación (polígono)] | [geología verdadera]
        #   [ley estimada escenario]    | [ley verdadera]
        # --------------------------------------------------------------
        nombre = active_sc["name"] if active_sc else "—"
        st.subheader(f"Comparación con la realidad — {nombre}")
        if active_sc is None:
            st.info("Mueva el slider «Escenario activo» para elegir qué "
                    "escenario comparar.")
        FS = (5.8, 5.2)   # mismo tamaño para las 4 vistas

        c1, c2 = st.columns(2)
        with c1:
            # Interpretación: polígono mineral del escenario activo
            st.pyplot(plotting.make_main_map(
                case, cutoff,
                scenario_polys=(active_sc["polygons"] if active_sc
                                else None),
                show_labels=False, point_size=18,
                title=f"Interpretación — {nombre}",
                figsize=FS), use_container_width=False)
        with c2:
            # Realidad: cuerpos mineralizados verdaderos
            st.pyplot(plotting.make_main_map(
                case, cutoff, show_truth=True, show_labels=False,
                point_size=18, title="Geología verdadera (3 cuerpos)",
                figsize=FS), use_container_width=False)

        c3, c4 = st.columns(2)
        with c3:
            # Ley estimada del escenario activo (por dominios)
            if active_est is not None:
                st.pyplot(plotting.make_main_map(
                    case, cutoff, layer="estimada", est=active_est,
                    scenario_polys=(active_sc["polygons"] if active_sc
                                    else None),
                    show_labels=False, point_size=18,
                    title=f"Ley estimada — {nombre}",
                    figsize=FS), use_container_width=False)
            else:
                st.info("Este escenario aún no tiene estimación "
                        "(presione «Estimar leyes»).")
        with c4:
            # Ley verdadera (misma escala Jet 0-1)
            st.pyplot(plotting.make_main_map(
                case, cutoff, layer="cu_true", show_labels=False,
                point_size=18, title="Ley verdadera Cu%",
                figsize=FS), use_container_width=False)

        if ss.scenarios:
            st.subheader("Acierto interpretativo por escenario")
            comp = reporting.compare_with_truth(ss.scenarios,
                                                case["truth_mask"],
                                                case["block_size"])
            fmt = {c: "{:,.0f}" for c in comp.columns if c.endswith("m²")}
            fmt["IoU"] = "{:.3f}"
            st.dataframe(comp.style.format(fmt), hide_index=True,
                         use_container_width=True)
            st.caption("IoU = intersección / unión (1 = interpretación "
                       "perfecta). Falso positivo: interpretado como mineral "
                       "pero estéril; falso negativo: mineral real omitido.")

            best = comp.loc[comp["IoU"].idxmax()]
            st.success(f"El escenario más parecido a la realidad es "
                       f"**{best['Escenario']}** (IoU = {best['IoU']:.3f}).")

        if active_est is not None and active_sc is not None:
            st.subheader(f"Error de estimación (estimado − verdadero) — "
                         f"{active_sc['name']}")
            err = active_est["est"] - case["cu_true"]
            fig = plotting.make_main_map(
                case, cutoff, show_labels=False, point_size=15,
                title=(f"Error de estimación (Cu% est − Cu% real) — "
                       f"{active_sc['name']}"),
                figsize=(6.8, 5.8))
            ax = fig.axes[0]
            plotting.draw_layer(ax, err, case["nx"], case["ny"],
                                case["block_size"], "RdBu_r", -0.6, 0.6,
                                "Error Cu%")
            st.pyplot(fig, use_container_width=False)


# ------------------------------------------------------------------
# VISTA 7: exportación
# ------------------------------------------------------------------
if view == "💾 Exportar":
    st.subheader("Exportar resultados")
    if not ss.scenarios:
        st.info("No hay escenarios guardados que exportar.")
    else:
        # --- Escenarios como JSON (sin arrays numpy) ---
        export = []
        for sc in ss.scenarios:
            export.append({
                "scenario_id": sc["scenario_id"], "name": sc["name"],
                "created_at": sc["created_at"],
                "polygons": [{"tipo": q["tipo"],
                              "coords": [[round(x, 2), round(y, 2)]
                                         for x, y in q["coords"]]}
                             for q in sc["polygons"]],
                "area_mineralizada_m2": sc["area_mineralizada"],
                "toneladas": sc["toneladas"],
                "ley_media": sc["ley_media"],
                "metal_contenido": sc["metal_contenido"],
                "estimated": sc["estimated"],
                "classified": sc["classified"],
            })
        st.download_button("📥 Escenarios (JSON)",
                           json.dumps(export, indent=2, ensure_ascii=False),
                           "escenarios.json", "application/json")

        estimados_x = [sc for sc in ss.scenarios if sc.get("est_result")]
        if estimados_x:
            totals = reporting.report_total_by_scenario(
                estimados_x, case["dist"], d_med, d_ind, d_inf,
                case["block_size"], espesor, densidad)
            st.download_button("📥 Recursos por escenario (CSV)",
                               totals.to_csv(index=False).encode("utf-8-sig"),
                               "recursos_por_escenario.csv", "text/csv")

            # Cada escenario se reporta con SU PROPIA estimación
            by_cat = pd.concat([
                reporting.report_resources_by_category(
                    sc["name"], sc["mask"],
                    classify_resources(case["dist"], sc["mask"],
                                       d_med, d_ind, d_inf),
                    sc["est_result"]["est"],
                    case["block_size"], espesor, densidad)
                for sc in estimados_x], ignore_index=True)
            st.download_button("📥 Recursos por categoría (CSV)",
                               by_cat.to_csv(index=False).encode("utf-8-sig"),
                               "recursos_por_categoria.csv", "text/csv")

            perc = reporting.scenario_percentiles(totals)
            st.download_button("📥 Resumen P5/P50/P95/I90 (CSV)",
                               perc.to_csv(index=False).encode("utf-8-sig"),
                               "resumen_percentiles.csv", "text/csv")
        else:
            st.caption("Estime leyes para habilitar los CSV de recursos.")
