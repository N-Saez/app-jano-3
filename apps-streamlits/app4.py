# streamlit_diluter_app_v1_18.py
# ------------------------------------------------------
# Etapas:
#   0. Cargar CSV + seleccionar columnas
#   1. Curado / homogeneización + ignorar (define qué códigos son 'ignorados')
#   2. Configurar absorb_length
#   3. Matriz de afinidad, Parámetros de Reasignación, Reglas de Absorción, Manejo de Ignorados y Gaps
#   4. Ejecutar Reasignación de Códigos por Bloques
#   5. Resultados (incluye fusión simple de bloques finales con control de gaps)
# ------------------------------------------------------

import streamlit as st
import pandas as pd
import numpy as np
import io

APP_VERSION = "v1.18a Alejandro" 
st.set_page_config(page_title=f"Dilución Geológica {APP_VERSION}", layout="wide")
# tratando de arreglar la lógica de los ignorados en la Opción B, tanto en la absorción como en afinidad. 
# --------------------- Backend Functions --------------------------

# --- FUNCIÓN DE REASIGNACIÓN DE CÓDIGOS BASADA EN BLOQUES (MODIFICADA) ---
def generate_block_based_code_reassignment_trace(
    df_input_trace, hole_col, from_col, to_col, geocode_col,
    absorb_lengths_dict, affinity_matrix_bool,
    activar_absorcion_bilateral, multiplicador_X,
    manejo_ignorados, 
    codigos_marcados_como_ignorados, 
    max_gap_dist,
    default_absorb_length_for_ignored_B, # <--- PARÁMETRO AÑADIDO 
    max_iter=5
):
    # df_input_trace: pd.DataFrame, DataFrame con los datos de entrada.
    # hole_col: str, Nombre de la columna de identificación de sondaje.
    # from_col: str, Nombre de la columna de profundidad inicial.
    # to_col: str, Nombre de la columna de profundidad final.
    # geocode_col: str, Nombre de la columna de geocódigos.
    # absorb_lengths_dict: dict, Mapeo de geocódigo a su longitud mínima de absorción.
    # affinity_matrix_bool: pd.DataFrame, Matriz de afinidad entre geocódigos.
    # activar_absorcion_bilateral: bool, Indica si se usa la regla de absorción bilateral.
    # multiplicador_X: float, Factor para ajustar los umbrales de longitud de absorción de vecinos.
    # manejo_ignorados: str, Estrategia para manejar códigos ignorados ('A' o 'B').
    # codigos_marcados_como_ignorados: list, Lista de códigos que se consideran ignorados.
    # max_gap_dist: float, Distancia máxima para que dos tramos con el mismo código se consideren un bloque continuo.
    # max_iter: int, Límite de iteraciones del algoritmo.

    if df_input_trace.empty:
        # empty_df: pd.DataFrame, DataFrame vacío para devolver si la entrada está vacía.
        empty_df = df_input_trace.copy()
        if geocode_col not in empty_df.columns and not empty_df.empty :
             st.error(f"GBB: Columna geocódigo '{geocode_col}' no existe.")
             return df_input_trace 
        elif not empty_df.empty: 
            empty_df[geocode_col] = empty_df[geocode_col]
            empty_df['geocode_iter_final'] = empty_df[geocode_col]
        else: 
            empty_df[geocode_col] = pd.Series(dtype='object')
            empty_df['geocode_iter_final'] = pd.Series(dtype='object')
        return empty_df

    df_trace_processing = df_input_trace.copy() 
        # df_trace_processing: pd.DataFrame, Copia del DataFrame de entrada para realizar modificaciones.
    if not all(c in df_trace_processing.columns for c in [hole_col, from_col, to_col, geocode_col]):
        st.error("GBB: Faltan columnas esenciales."); return df_input_trace 
    try:
        df_trace_processing[from_col] = pd.to_numeric(df_trace_processing[from_col])
        df_trace_processing[to_col] = pd.to_numeric(df_trace_processing[to_col])
    except Exception as e: st.error(f"GBB: Error FROM/TO a numérico: {e}"); return df_input_trace

    df_trace_processing['original_interval_id'] = df_trace_processing.index
    df_trace_processing['interval_length'] = df_trace_processing[to_col] - df_trace_processing[from_col]
    df_valid_intervals = df_trace_processing[df_trace_processing['interval_length'] > 0].copy()
    
    if df_valid_intervals.empty:
        st.info("GBB: No hay intervalos con longitud válida.")
        output_df = df_input_trace.copy()
        if geocode_col in output_df.columns:
            output_df[geocode_col] = output_df[geocode_col] 
            output_df['geocode_iter_final'] = output_df[geocode_col]
        else:
            output_df[geocode_col] = pd.Series(dtype='object', index=output_df.index)
            output_df['geocode_iter_final'] = pd.Series(dtype='object', index=output_df.index)
        return output_df

    iter_codes = df_valid_intervals.set_index('original_interval_id')[geocode_col].copy()
    df_iter_results = pd.DataFrame(index=iter_codes.index)
    df_iter_results[geocode_col] = iter_codes.copy() 

    all_hole_ids = df_valid_intervals[hole_col].unique()
    # Ciclo principal de iteraciones de reasignación de códigos. 
    for iter_num in range(1, max_iter + 1):
        # iter_name: str, Nombre de la columna para esta iteración (ej: 'geocode_iter_01').
        iter_name = f'geocode_iter_{iter_num:02d}'
        # new_codes_for_iter_main: pd.Series, Copia de iter_codes para acumular los cambios de esta iteración principal.
        new_codes_for_iter_main = iter_codes.copy() 
        # changed_in_this_main_iter: bool, Bandera para detectar si hubo algún cambio de código en esta iteración principal.
        changed_in_this_main_iter = False
         # Procesamiento sondaje por sondaje.
        for hole_id in all_hole_ids:
            # hole_intervals_df: pd.DataFrame, Subconjunto de intervalos válidos para el sondaje actual, ordenados por profundidad.
            hole_intervals_df = df_valid_intervals[df_valid_intervals[hole_col] == hole_id].sort_values(by=from_col)
            if hole_intervals_df.empty: continue
            # current_hole_valid_indices: list, Lista de 'original_interval_id' para los intervalos del sondaje actual.
            current_hole_valid_indices = hole_intervals_df['original_interval_id'].tolist()
            if not current_hole_valid_indices: continue
            # codes_at_start_of_iter: pd.Series, Geocódigos de los intervalos del sondaje actual al inicio de esta iteración principal.
            codes_at_start_of_iter = iter_codes.loc[current_hole_valid_indices]
            lengths_at_start_of_iter = hole_intervals_df.set_index('original_interval_id')['interval_length'].reindex(current_hole_valid_indices)
            from_vals_at_start_of_iter = hole_intervals_df.set_index('original_interval_id')[from_col].reindex(current_hole_valid_indices)
            to_vals_at_start_of_iter = hole_intervals_df.set_index('original_interval_id')[to_col].reindex(current_hole_valid_indices)


            # blocks: list, Lista de diccionarios, donde cada diccionario representa un "bloque" de código continuo. 
            blocks = []
            if codes_at_start_of_iter.empty: continue
             # Variables para construir el bloque actual mientras se recorren los intervalos.
            current_block_indices, current_block_code, current_block_len = [], None, 0.0
            # last_to_val: float, Valor 'TO' del último intervalo añadido al bloque actual, para calcular el gap.
            last_to_val = -float('inf') 

            # Identificación de Bloques con control de Gaps.
            for original_idx in current_hole_valid_indices:
                code = codes_at_start_of_iter.loc[original_idx]
                length = lengths_at_start_of_iter.loc[original_idx]
                current_from_val = from_vals_at_start_of_iter.loc[original_idx]
                # gap: float, Distancia entre el TO del intervalo anterior del bloque y el FROM del actual.
                gap = current_from_val - last_to_val if current_block_indices else 0 


                # Condiciones para iniciar un nuevo bloque:
                # 1. Es el primer intervalo.
                # 2. El código del intervalo actual es diferente al del bloque que se está formando.
                # 3. El gap dist con el intervalo anterior del bloque supera max_gap_dist.

                if not current_block_indices or code != current_block_code or gap > max_gap_dist:
                    if current_block_indices: 
                        blocks.append({'indices': list(current_block_indices), 'code': current_block_code, 'length': current_block_len, 
                                       'from': from_vals_at_start_of_iter.loc[current_block_indices[0]], 
                                       'to': to_vals_at_start_of_iter.loc[current_block_indices[-1]]})
                    current_block_indices, current_block_code, current_block_len = [original_idx], code, length
                else: 
                    current_block_indices.append(original_idx); current_block_len += length
                last_to_val = to_vals_at_start_of_iter.loc[original_idx]

            if current_block_indices: 
                blocks.append({'indices': list(current_block_indices), 'code': current_block_code, 'length': current_block_len,
                               'from': from_vals_at_start_of_iter.loc[current_block_indices[0]], 
                               'to': to_vals_at_start_of_iter.loc[current_block_indices[-1]]})
            if not blocks: continue
            
            codes_snapshot_for_hole = new_codes_for_iter_main.loc[current_hole_valid_indices].copy()

            for i_block in range(len(blocks)):
                current_block_def = blocks[i_block]
                code_of_current_block = current_block_def['code']
                is_current_block_ignored = str(code_of_current_block) in codigos_marcados_como_ignorados

                if is_current_block_ignored and manejo_ignorados == "A": continue

                min_len_for_current_block = absorb_lengths_dict.get(code_of_current_block, float('inf'))
                if is_current_block_ignored and manejo_ignorados == "B" and code_of_current_block not in absorb_lengths_dict:
                    min_len_for_current_block = default_absorb_length_for_ignored_B 

                if current_block_def['length'] < min_len_for_current_block: 
                    target_code_to_absorb_with = None 
                    if activar_absorcion_bilateral:
                        if i_block > 0 and i_block < len(blocks) - 1: 
                            prev_b_def, next_b_def = blocks[i_block-1], blocks[i_block+1]
                            if prev_b_def['code'] == next_b_def['code']: 
                                common_neighbor_code = prev_b_def['code']
                                is_neighbor_code_ignored = str(common_neighbor_code) in codigos_marcados_como_ignorados
                                
                                if is_neighbor_code_ignored and manejo_ignorados == "A": # Iggnorados tipo A no absorben ni son absorbidos
                                    pass
                                else:
                                    combined_len = prev_b_def['length'] + next_b_def['length']
                                    absorb_len_neighbor = absorb_lengths_dict.get(common_neighbor_code, float('inf'))
                                    if combined_len > multiplicador_X * absorb_len_neighbor:
                                        if manejo_ignorados == "B" and (is_current_block_ignored or is_neighbor_code_ignored) and \
                                            not (str(common_neighbor_code) in codigos_marcados_como_ignorados):
                                            affinity = True
                                        else:
                                            # logica de afinidad normal
                                            affinity = (code_of_current_block == common_neighbor_code) or \
                                                   (code_of_current_block in affinity_matrix_bool.index and \
                                                    common_neighbor_code in affinity_matrix_bool.columns and \
                                                    affinity_matrix_bool.loc[code_of_current_block, common_neighbor_code])
                                        if affinity: target_code_to_absorb_with = common_neighbor_code
                    
                    if target_code_to_absorb_with is None and not activar_absorcion_bilateral: 
                        prev_b_apt, next_b_apt = False, False
                        prev_b_data, next_b_data = None, None
                        if i_block > 0:
                            prev_b_temp = blocks[i_block-1]
                            is_prev_ignored_absorbent = str(prev_b_temp['code']) in codigos_marcados_como_ignorados and manejo_ignorados in ["A", "B"]
                            if not is_prev_ignored_absorbent and \
                               prev_b_temp['length'] >= multiplicador_X * absorb_lengths_dict.get(prev_b_temp['code'], float('inf')):
                                prev_b_apt, prev_b_data = True, prev_b_temp
                        if i_block < len(blocks) - 1:
                            next_b_temp = blocks[i_block+1]
                            is_next_ignored_absorbent = str(next_b_temp['code']) in codigos_marcados_como_ignorados and manejo_ignorados in ["A", "B"]
                            if not is_next_ignored_absorbent and \
                               next_b_temp['length'] >= multiplicador_X * absorb_lengths_dict.get(next_b_temp['code'], float('inf')):
                                next_b_apt, next_b_data = True, next_b_temp
                        
                        temp_target_code = None
                        if prev_b_apt and next_b_apt: temp_target_code = prev_b_data['code'] if prev_b_data['length'] >= next_b_data['length'] else next_b_data['code']
                        elif prev_b_apt: temp_target_code = prev_b_data['code']
                        elif next_b_apt: temp_target_code = next_b_data['code']
                        
                        if temp_target_code:
                            # affinity: bool, Determina si hay afinidad para la absorción.
                            affinity = False # Inicializar
                            # Condición especial para ignorados Opción B siendo absorbidos por un válido
                            # is_temp_target_code_valid_absorbent: bool, True si el vecino no es un ignorado que no puede absorber.
                            is_temp_target_code_valid_absorbent = not (str(temp_target_code) in codigos_marcados_como_ignorados and manejo_ignorados in ["A", "B"])
                            if manejo_ignorados == "B" and is_current_block_ignored and is_temp_target_code_valid_absorbent:
                                affinity = True # Asumir afinidad
                            elif  is_temp_target_code_valid_absorbent: # Solo chequear afinidad de matriz si el target es un absorbente válido   
                                    # Logica de afinidad normalquiz
                                    affinity = (code_of_current_block == temp_target_code) or \
                                       (code_of_current_block in affinity_matrix_bool.index and \
                                        temp_target_code in affinity_matrix_bool.columns and \
                                        affinity_matrix_bool.loc[code_of_current_block, temp_target_code])
                            if affinity: target_code_to_absorb_with = temp_target_code

                    if target_code_to_absorb_with:
                        # Aplicar cambio solo si el bloque actual no es un 'ignorado fijo' (Opción A)
                        if not (is_current_block_ignored and manejo_ignorados == "A"):
                            for idx_orig in current_block_def['indices']:
                                if codes_snapshot_for_hole.loc[idx_orig] != target_code_to_absorb_with:
                                    codes_snapshot_for_hole.loc[idx_orig] = target_code_to_absorb_with
                                    changed_in_this_main_iter = True
            new_codes_for_iter_main.loc[current_hole_valid_indices] = codes_snapshot_for_hole
        
        df_iter_results[iter_name] = new_codes_for_iter_main
        if not changed_in_this_main_iter:
            st.success(f"Convergencia de reasignación de códigos  alcanzada en iteración {iter_num}.")
            break
        iter_codes = new_codes_for_iter_main.copy()
        if iter_num == max_iter:
            st.warning(f"Se alcanzó el máx. de iteraciones ({max_iter}) para reasignación.")

    df_iter_results["geocode_iter_final"] = iter_codes
    df_output_trace = df_input_trace.copy() 
    for col_iter_name in df_iter_results.columns: 
        if col_iter_name == geocode_col and geocode_col in df_output_trace.columns:
             df_output_trace[col_iter_name].update(df_iter_results[col_iter_name])
        else: df_output_trace[col_iter_name] = df_iter_results[col_iter_name].reindex(df_output_trace.index)
        if geocode_col in df_output_trace.columns:
            mask_fill = df_output_trace[col_iter_name].isna()
            df_output_trace.loc[mask_fill, col_iter_name] = df_output_trace.loc[mask_fill, geocode_col]
        else: df_output_trace.loc[df_output_trace[col_iter_name].isna(), col_iter_name] = "INDEFINIDO"
    return df_output_trace

# --- FUNCIÓN PARA FUSIÓN SIMPLE DE CÓDIGOS CONSECUTIVOS ---
def merge_final_block_codes(df_with_final_codes, hole_col, from_col, to_col, 
                            final_geocode_col, original_cols_to_preserve, max_gap_dist):
    output_geocode_name = final_geocode_col.replace('_iter_final', '') if '_iter_final' in final_geocode_col else 'geocode'
    expected_out_cols = list(original_cols_to_preserve); 
    if hole_col not in expected_out_cols: expected_out_cols.insert(0, hole_col)
    expected_out_cols.extend([from_col, to_col, output_geocode_name]); 
    expected_out_cols = list(dict.fromkeys(expected_out_cols))
    if df_with_final_codes.empty or not all(c in df_with_final_codes.columns for c in [hole_col, from_col, to_col, final_geocode_col]):
        return pd.DataFrame(columns=expected_out_cols)
    merged_data = []
    valid_original_cols_to_preserve = [c for c in original_cols_to_preserve if c in df_with_final_codes.columns and c not in [hole_col, from_col, to_col, final_geocode_col]]
    for hole_id, group in df_with_final_codes.groupby(hole_col):
        group = group.sort_values(by=from_col).reset_index(drop=True)
        if group.empty: continue
        current_from_val = group.loc[0, from_col]; current_to_val = group.loc[0, to_col]
        current_code_val = group.loc[0, final_geocode_col]
        current_other_cols_data = {col: group.loc[0, col] for col in valid_original_cols_to_preserve}
        for i in range(1, len(group)):
            gap_to_current = group.loc[i, from_col] - current_to_val
            if group.loc[i, final_geocode_col] != current_code_val or \
               pd.isna(group.loc[i, final_geocode_col]) != pd.isna(current_code_val) or \
               gap_to_current > max_gap_dist: 
                block_data = {hole_col: hole_id, from_col: current_from_val, to_col: current_to_val, output_geocode_name: current_code_val}
                block_data.update(current_other_cols_data); merged_data.append(block_data)
                current_from_val = group.loc[i, from_col]; current_code_val = group.loc[i, final_geocode_col]
                current_other_cols_data = {col: group.loc[i, col] for col in valid_original_cols_to_preserve}
            current_to_val = group.loc[i, to_col]
        block_data_final = {hole_col: hole_id, from_col: current_from_val, to_col: current_to_val, output_geocode_name: current_code_val}
        block_data_final.update(current_other_cols_data); merged_data.append(block_data_final)
    if not merged_data: return pd.DataFrame(columns=expected_out_cols)
    return pd.DataFrame(merged_data)

# --- OTRAS FUNCIONES DE POSTPROCESO ---
def calculate_geocode_proportions(df, geocode_col_name, from_col_name, to_col_name):
    cols_to_return = [geocode_col_name, 'total_length', 'proportion_numeric', 'proportion_str']
    if df.empty or not all(c in df.columns for c in [geocode_col_name, from_col_name, to_col_name]): return pd.DataFrame(columns=cols_to_return)
    temp_df = df.copy()
    try: temp_df[from_col_name]=pd.to_numeric(temp_df[from_col_name]); temp_df[to_col_name]=pd.to_numeric(temp_df[to_col_name])
    except Exception: st.error(f"Error numérico en proporciones."); return pd.DataFrame(columns=cols_to_return)
    temp_df['length'] = temp_df[to_col_name] - temp_df[from_col_name]; temp_df = temp_df[temp_df['length'] > 0] 
    if temp_df.empty: return pd.DataFrame(columns=cols_to_return)
    summary = temp_df.groupby(geocode_col_name)['length'].sum().reset_index(name='total_length')
    total_overall_length = summary['total_length'].sum()
    summary['proportion_numeric'] = (summary['total_length']/total_overall_length*100) if total_overall_length > 0 else 0.0
    summary = summary.sort_values(by='total_length', ascending=False).reset_index(drop=True)
    summary['proportion_str'] = summary['proportion_numeric'].round(2).astype(str) + '%'
    return summary[cols_to_return]

def calculate_change_matrix(df_trace, orig_geocode_col, final_geocode_col, from_col, to_col):
    if df_trace.empty or not all(c in df_trace.columns for c in [orig_geocode_col,final_geocode_col,from_col,to_col]): return pd.DataFrame()
    temp_df = df_trace.copy()
    try: temp_df[from_col]=pd.to_numeric(temp_df[from_col]); temp_df[to_col]=pd.to_numeric(temp_df[to_col])
    except Exception: st.error(f"Error numérico en matriz cambio."); return pd.DataFrame()
    temp_df['len_matrix'] = temp_df[to_col] - temp_df[from_col]
    temp_df = temp_df.dropna(subset=[orig_geocode_col,final_geocode_col,'len_matrix']); temp_df = temp_df[temp_df['len_matrix'] > 0]
    if temp_df.empty: return pd.DataFrame()
    temp_df[orig_geocode_col]=temp_df[orig_geocode_col].astype(str); temp_df[final_geocode_col]=temp_df[final_geocode_col].astype(str)
    return pd.crosstab(temp_df[orig_geocode_col], temp_df[final_geocode_col], values=temp_df['len_matrix'], aggfunc='sum').fillna(0)

def calculate_cumulative_change_per_iteration(df_trace, base_geocode_col, from_col, to_col):
    if df_trace.empty : st.warning("DF trazabilidad vacío."); return pd.DataFrame(columns=['Iteración','Metros Acumulados de Cambio'])
    if base_geocode_col not in df_trace.columns: st.error(f"Columna base '{base_geocode_col}' no encontrada."); return pd.DataFrame(columns=['Iteración','Metros Acumulados de Cambio'])
    df_calc = df_trace.copy()
    try:
        df_calc['len_calc'] = pd.to_numeric(df_calc[to_col],errors='coerce') - pd.to_numeric(df_calc[from_col],errors='coerce')
        df_calc = df_calc.dropna(subset=['len_calc']); df_calc = df_calc[df_calc['len_calc'] > 0]
    except Exception as e: st.error(f"Error calculando 'len_calc': {e}"); return pd.DataFrame(columns=['Iteración','Metros Acumulados de Cambio'])
    if df_calc.empty: st.info("No hay intervalos válidos para trazabilidad."); return pd.DataFrame(columns=['Iteración','Metros Acumulados de Cambio'])
    iter_cols = sorted([c for c in df_calc.columns if c.startswith('geocode_iter_') and c != 'geocode_iter_final'])
    stages = [base_geocode_col] + iter_cols
    if 'geocode_iter_final' in df_calc.columns and 'geocode_iter_final' not in stages: stages.append('geocode_iter_final')
    valid_stages = [c for c in stages if c in df_calc.columns]
    for c in valid_stages: df_calc[c] = df_calc[c].astype(str)
    cum_m = 0.0; plot_data = {'Iteración':[],'Metros Acumulados de Cambio':[]}
    if len(valid_stages) < 2: st.info("No hay suficientes etapas para gráfico."); return pd.DataFrame(plot_data)
    for i in range(len(valid_stages)-1):
        prev, curr = valid_stages[i], valid_stages[i+1]
        changed = (df_calc[curr] != df_calc[prev])
        m_changed = df_calc.loc[changed, 'len_calc'].sum(); cum_m += m_changed
        plot_data['Iteración'].append(i+1); plot_data['Metros Acumulados de Cambio'].append(round(cum_m,2))
    return pd.DataFrame(plot_data)

SOSPECHOSOS = ["0", "-99", "999", "NONE", "N/A", "NULL", "SIN DATO", "NOMOD", "SR", "", " ", "nan", "NAN"]

# --- SESSION STATE ---
if "fase" not in st.session_state:
    st.session_state.fase = 0
    st.session_state.df_original = None; st.session_state.uploaded_file_name = None
    st.session_state.cols_sel = {} 
    st.session_state.equiv_edit = pd.DataFrame(); st.session_state.equiv_edit_source_col = None
    st.session_state.equiv_final = pd.DataFrame(); st.session_state.equiv_final_source_col = None
    st.session_state.absorb_df = pd.DataFrame() # pd.DataFrame: Almacena los 'absorb_length' para cada geocódigo activo (Fase 2).
    st.session_state.default_absorb_length_setting = 1.5 # float: Valor por defecto para 'absorb_length' (Fase 2).
    st.session_state.affinity_exception_rules = [] # list: Lista de frozensets de pares de códigos que NO son afines (Fase 3).
    st.session_state.selected_principal_for_exceptions = None
    st.session_state.df_active_for_processing = None 
    st.session_state.df_block_reassigned_trace = None 
    st.session_state.diluted_df_simple_merge = None 
    st.session_state.max_iterations_reassign = 10
    st.session_state.activar_absorcion_bilateral = False 
    st.session_state.multiplicador_X_absorcion = 1.0
    st.session_state.manejo_ignorados = "A" # "A": Fijos, no absorbentes; "B": Absorbibles, no absorbentes
    st.session_state.max_gap_dist = 0.1 

st.title(f"💧🪨 Dilución Geológica – Flujo por Etapas {APP_VERSION}")
st.markdown("---")
cont0, cont1, cont2, cont3, cont4, cont5 = st.container(), st.container(), st.container(), st.container(), st.container(), st.container()

# --- FASE 0: Carga y Selección ---
with cont0:
    st.header("Fase 0: Carga de Datos y Selección de Columnas")
    uploaded_file = st.file_uploader("Cargar archivo CSV de sondajes", type="csv", key=f"fileuploader_f0_{APP_VERSION}")
    if uploaded_file and (st.session_state.df_original is None or uploaded_file.name != st.session_state.uploaded_file_name):
        try:
            st.session_state.df_original = pd.read_csv(uploaded_file); st.session_state.uploaded_file_name = uploaded_file.name
            st.session_state.fase = 0; st.session_state.cols_sel = {}
            st.session_state.equiv_edit, st.session_state.equiv_edit_source_col = pd.DataFrame(), None
            st.session_state.equiv_final, st.session_state.equiv_final_source_col = pd.DataFrame(), None
            st.session_state.absorb_df = pd.DataFrame(); st.session_state.affinity_exception_rules = []
            st.session_state.selected_principal_for_exceptions = None; st.session_state.df_active_for_processing = None
            st.session_state.df_block_reassigned_trace = None; st.session_state.diluted_df_simple_merge = None
            st.session_state.activar_absorcion_bilateral = False; st.session_state.multiplicador_X_absorcion = 1.0
            st.session_state.manejo_ignorados = "A"; st.session_state.max_gap_dist = 0.1
            st.success(f"Archivo '{uploaded_file.name}' cargado."); st.rerun()
        except Exception as e: st.error(f"Error al cargar: {e}"); st.session_state.df_original = None
    if st.session_state.df_original is not None:
        df_display_f0 = st.session_state.df_original; st.subheader("Vista previa (primeras 5 filas):"); st.dataframe(df_display_f0.head())
        available_cols_f0 = df_display_f0.columns.tolist(); available_cols_lower_f0 = [c.lower() for c in available_cols_f0]
        def find_col_pref_f0(prefs,cur,fb_idx=0):
            if cur and cur in available_cols_f0: return cur
            for p in prefs: 
                try: return available_cols_f0[available_cols_lower_f0.index(p.lower())]
                except ValueError: continue
            return available_cols_f0[min(fb_idx,len(available_cols_f0)-1)] if available_cols_f0 else None
        sel_c_f0 = st.session_state.cols_sel
        def_hole = find_col_pref_f0(["dhid","hole_id","sondaje"], sel_c_f0.get("hole"),0)
        def_from = find_col_pref_f0(["from","desde"], sel_c_f0.get("from"),1)
        def_to = find_col_pref_f0(["to","hasta"], sel_c_f0.get("to"),2)
        def_geo = find_col_pref_f0(["litho","geocode","rock","lito","geology"], sel_c_f0.get("geocode_original"),3)
        idx = lambda v,f: available_cols_f0.index(v) if v and v in available_cols_f0 else f
        if not available_cols_f0: st.warning("CSV vacío.")
        else:
            c_hole = st.selectbox("ID Sondaje:", available_cols_f0, idx(def_hole,0), key=f"sel_h_f0_{APP_VERSION}")
            c_from = st.selectbox("Desde:", available_cols_f0, idx(def_from,1 if len(available_cols_f0)>1 else 0), key=f"sel_f_f0_{APP_VERSION}")
            c_to = st.selectbox("Hasta:", available_cols_f0, idx(def_to,2 if len(available_cols_f0)>2 else 0), key=f"sel_t_f0_{APP_VERSION}")
            c_geo_orig = st.selectbox("Cód. Lito Original:", available_cols_f0, idx(def_geo,3 if len(available_cols_f0)>3 else 0), key=f"sel_go_f0_{APP_VERSION}")
            if st.button("Continuar a Curado", key=f"btn_f0_{APP_VERSION}"):
                try:
                    if not all(c in df_display_f0 for c in [c_from,c_to,c_hole,c_geo_orig]): st.error("Columna(s) no existen."); st.stop()
                    pd.to_numeric(df_display_f0[c_from]); pd.to_numeric(df_display_f0[c_to])
                    st.session_state.cols_sel = {"hole":c_hole,"from":c_from,"to":c_to,"geocode_original":c_geo_orig,"geocode_col_for_processing":"geocode_curado"}
                    st.session_state.fase = 1; st.rerun()
                except ValueError: st.error(f"'{c_from}'/'{c_to}' deben ser numéricas.")
                except KeyError as e: st.error(f"Error columnas: {e}.")
    st.markdown("---")

# --- FASE 1: Curado de Códigos Litológicos ---
if st.session_state.fase >= 1 and st.session_state.df_original is not None and st.session_state.cols_sel:
    with cont1:
        st.header("Fase 1: Curado de Códigos Litológicos")
        df_f1 = st.session_state.df_original.copy()
        original_geocode_col_f1 = st.session_state.cols_sel["geocode_original"]
        curated_geocode_col_f1 = st.session_state.cols_sel["geocode_col_for_processing"]
        df_f1["_orig_str_f1"] = df_f1[original_geocode_col_f1].astype(str).fillna("")
        df_f1[curated_geocode_col_f1] = df_f1["_orig_str_f1"].str.strip().str.upper()
        if st.session_state.equiv_edit.empty or st.session_state.get("equiv_edit_source_col") != original_geocode_col_f1:
            if not st.session_state.equiv_final.empty and st.session_state.get("equiv_final_source_col") == original_geocode_col_f1 and \
               curated_geocode_col_f1 in st.session_state.equiv_final.columns and original_geocode_col_f1 in st.session_state.equiv_final.columns:
                st.session_state.equiv_edit = st.session_state.equiv_final.copy()
            else: 
                equiv_data_f1 = df_f1.groupby("_orig_str_f1")[curated_geocode_col_f1].first().reset_index().rename(columns={"_orig_str_f1": original_geocode_col_f1})
                counts_f1 = df_f1[original_geocode_col_f1].value_counts().reset_index(name="registros")
                temp_equiv_df_f1 = pd.merge(equiv_data_f1, counts_f1, on=original_geocode_col_f1, how="left")
                temp_equiv_df_f1["ignorar"] = temp_equiv_df_f1[curated_geocode_col_f1].apply(lambda x: str(x).strip().upper() in SOSPECHOSOS or pd.isna(x) or str(x).strip() == "")
                st.session_state.equiv_edit = temp_equiv_df_f1[[original_geocode_col_f1, curated_geocode_col_f1, "registros", "ignorar"]].copy()
            st.session_state.equiv_edit_source_col = original_geocode_col_f1
        if not st.session_state.equiv_edit.empty:
            cfg_f1 = {original_geocode_col_f1:st.column_config.TextColumn(disabled=True), curated_geocode_col_f1:st.column_config.TextColumn(label="Geocódigo Curado (Editable)")}
            edited_equiv_f1 = st.data_editor(st.session_state.equiv_edit,column_config=cfg_f1,num_rows="dynamic",key=f"ed_equiv_f1_{APP_VERSION}")
            if not edited_equiv_f1.equals(st.session_state.equiv_edit): st.session_state.equiv_edit = edited_equiv_f1.reset_index(drop=True) 
        else: st.info("Tabla de equivalencias no generada.")
        if st.button("Guardar Curado y Continuar", key=f"btn_f1_{APP_VERSION}"):
            if st.session_state.equiv_edit.empty or curated_geocode_col_f1 not in st.session_state.equiv_edit.columns: st.error("Tabla de curado vacía o incorrecta.")
            else:
                st.session_state.equiv_final = st.session_state.equiv_edit.copy(); st.session_state.equiv_final_source_col = st.session_state.get("equiv_edit_source_col") 
                st.session_state.fase = 2; st.session_state.absorb_df = pd.DataFrame(); st.session_state.affinity_exception_rules = []
                st.session_state.selected_principal_for_exceptions = None; st.session_state.df_active_for_processing = None
                st.session_state.df_block_reassigned_trace = None; st.session_state.diluted_df_simple_merge = None
                st.success("Curado guardado."); st.rerun()
    st.markdown("---")

# --- FASE 2: Configuración de absorb_length ---
if st.session_state.fase >= 2 and not st.session_state.equiv_final.empty:
    with cont2:
        st.header("Fase 2: Configuración de Longitud Mínima de Absorción (`absorb_length`)")
        curated_geocode_col_f2 = st.session_state.cols_sel["geocode_col_for_processing"]
        # Usar códigos de equiv_final que NO están marcados como ignorar para definir absorb_length
        # A menos que se decida que los "ignorados" también pueden tener un absorb_length (si Opción B se usa)
        # Por ahora, solo los no ignorados. Se puede ajustar si manejo_ignorados="B" requiere que tengan absorb_length.
        codes_for_absorb_df = sorted(st.session_state.equiv_final[~st.session_state.equiv_final["ignorar"]][curated_geocode_col_f2].astype(str).unique())
        codes_for_absorb_df = [g for g in codes_for_absorb_df if pd.notna(g) and str(g).strip() and str(g).strip().upper() not in SOSPECHOSOS]

        if not codes_for_absorb_df: st.warning("No hay códigos activos (no ignorados) para configurar `absorb_length`. Revise Fase 1.")
        else:
            if st.session_state.absorb_df.empty or set(st.session_state.absorb_df.get('geocode',pd.Series(dtype=str))) != set(codes_for_absorb_df):
                existing_map_f2 = {}
                if not st.session_state.absorb_df.empty and 'geocode' in st.session_state.absorb_df.columns:
                    existing_map_f2 = dict(zip(st.session_state.absorb_df['geocode'], st.session_state.absorb_df['absorb_length']))
                st.session_state.absorb_df = pd.DataFrame([{'geocode':c,'absorb_length':existing_map_f2.get(c,1.0)} for c in codes_for_absorb_df])
            st.write("Define `absorb_length` para cada geocódigo curado activo (no ignorado).")
            c1_f2,_ = st.columns([1,3]); val_all_f2 = c1_f2.number_input("Asignar a todos e ignorados:",0.0,100.0,0.5,format="%.2f",key=f"all_abs_f2_{APP_VERSION}")
            if c1_f2.button("Aplicar",key=f"btn_all_abs_f2_{APP_VERSION}"):
                if not st.session_state.absorb_df.empty: st.session_state.absorb_df['absorb_length']=val_all_f2
                st.session_state.default_absorb_length_setting = val_all_f2
                st.rerun()
            if not st.session_state.absorb_df.empty:
                edited_abs_f2 = st.data_editor(st.session_state.absorb_df, column_config={"geocode":st.column_config.TextColumn(disabled=True)},num_rows="fixed",key=f"ed_abs_f2_{APP_VERSION}")
                if not edited_abs_f2.equals(st.session_state.absorb_df): st.session_state.absorb_df = edited_abs_f2.reset_index(drop=True)
            else: st.info("No hay códigos para configurar `absorb_length`.")
            if st.button("Continuar a Afinidad", key=f"btn_f2_{APP_VERSION}"):
                if st.session_state.absorb_df.empty and codes_for_absorb_df: st.warning("Configure `absorb_length`.")
                elif not codes_for_absorb_df: st.warning("No hay códigos activos. Revise Fase 1.")
                else:
                    st.session_state.fase = 3; st.session_state.affinity_exception_rules=[]; st.session_state.selected_principal_for_exceptions=None
                    st.session_state.default_absorb_length_setting = val_all_f2
                    st.session_state.df_active_for_processing=None; st.session_state.df_block_reassigned_trace=None; st.session_state.diluted_df_simple_merge=None
                    st.success("`absorb_length` guardado."); st.rerun()
        st.markdown("---")

# --- FASE 3: Afinidad, Parámetros de Reasignación y Reglas de Absorción ---
if st.session_state.fase >= 3: 
    with cont3:
        st.header("Fase 3: Afinidad, Parámetros de Reasignación y Reglas de Absorción")
        if st.session_state.absorb_df.empty: st.warning("Complete Fase 2 (Absorb_length) primero.")
        else:
            geocodes_activos_f3 = sorted(st.session_state.absorb_df['geocode'].astype(str).unique().tolist())
            if not geocodes_activos_f3: st.warning("No hay códigos activos para afinidad.")
            else:
                if 'selected_principal_for_exceptions' not in st.session_state or st.session_state.selected_principal_for_exceptions not in geocodes_activos_f3:
                    st.session_state.selected_principal_for_exceptions = geocodes_activos_f3[0] if geocodes_activos_f3 else None
                col_manage_f3, col_display_f3 = st.columns([2,3])
                with col_manage_f3: # UI Afinidad
                    st.subheader("Gestionar Excepciones de Afinidad")
                    def on_principal_change_f3(): st.session_state.selected_principal_for_exceptions = st.session_state.get(f"sb_principal_f3_{APP_VERSION}")
                    idx_principal_f3 = 0
                    if st.session_state.selected_principal_for_exceptions in geocodes_activos_f3: idx_principal_f3 = geocodes_activos_f3.index(st.session_state.selected_principal_for_exceptions)
                    st.selectbox("Código Principal:",geocodes_activos_f3,index=idx_principal_f3,key=f"sb_principal_f3_{APP_VERSION}",on_change=on_principal_change_f3)
                    current_principal_f3 = st.session_state.selected_principal_for_exceptions
                    if current_principal_f3:
                        options_multi_f3 = [g for g in geocodes_activos_f3 if g != current_principal_f3]
                        default_non_affine_f3 = [list(ex-{current_principal_f3})[0] for ex in st.session_state.affinity_exception_rules if current_principal_f3 in ex and list(ex-{current_principal_f3}) and list(ex-{current_principal_f3})[0] in options_multi_f3]
                        selected_non_affine_f3 = st.multiselect(f"'{current_principal_f3}' NO es afín con:",options_multi_f3,default=default_non_affine_f3,key=f"ms_non_affine_f3_{APP_VERSION}_{current_principal_f3}")
                        if st.button(f"Guardar Excepciones para '{current_principal_f3}'",key=f"btn_save_ex_f3_{APP_VERSION}_{current_principal_f3}"):
                            new_ex_list = [ex for ex in st.session_state.affinity_exception_rules if current_principal_f3 not in ex]
                            for non_aff_code in selected_non_affine_f3: new_ex_list.append(frozenset({current_principal_f3,non_aff_code}))
                            st.session_state.affinity_exception_rules = list(set(new_ex_list)); st.rerun()
                with col_display_f3: # Mostrar Matriz
                    st.subheader("Matriz de Afinidad Resultante")
                    affinity_matrix_f3 = pd.DataFrame(True,index=geocodes_activos_f3,columns=geocodes_activos_f3,dtype=bool); np.fill_diagonal(affinity_matrix_f3.values,False)
                    for ex_pair in st.session_state.affinity_exception_rules: c1,c2=tuple(ex_pair); affinity_matrix_f3.loc[c1,c2]=False; affinity_matrix_f3.loc[c2,c1]=False
                    display_aff_f3 = affinity_matrix_f3.where(np.tril(np.ones(affinity_matrix_f3.shape),k=-1).astype(bool))
                    if not display_aff_f3.empty: st.dataframe(display_aff_f3.dropna(axis=0,how='all').dropna(axis=1,how='all'))
                    elif geocodes_activos_f3: st.info("Más de 1 código activo para matriz.")
                    else: st.info("No hay códigos para matriz.")
                    st.session_state.affinity_for_backend = affinity_matrix_f3.copy()
            
            st.markdown("---"); st.subheader("Reglas Adicionales y Parámetros de Iteración")
            st.session_state.manejo_ignorados = st.selectbox("Manejo de Tramos 'Ignorados':", options=["A","B"], index=["A","B"].index(st.session_state.get("manejo_ignorados","A")), format_func=lambda x: "A: Fijos (no se absorben/ ni absorben)" if x=="A" else "B: Absorbibles (no absorben)", key=f"sel_ign_{APP_VERSION}", help="A: Ignorados no cambian ni absorben. B: Ignorados pueden ser absorbidos por no-ignorados, pero no absorben.")
            st.session_state.activar_absorcion_bilateral = st.checkbox("Activar Absorción Bilateral", value=st.session_state.get("activar_absorcion_bilateral",False), key=f"cb_bil_{APP_VERSION}", help="Un bloque corto se absorbe si AMBOS vecinos tienen MISMO código y SUMA largos > X*absorb_length_vecino.")
            st.session_state.multiplicador_X_absorcion = st.number_input("Multiplicador (X) para Long. de Vecinos:",min_value=0.1,value=st.session_state.get("multiplicador_X_absorcion",1.0),step=0.1,format="%.1f",key=f"num_X_{APP_VERSION}",help="Si largo de vecino(s) >  X*'absorb_length' del vecino(s). Usado en ambas lógicas.")
            st.session_state.max_gap_dist = st.number_input("Máx. Distancia de Gap para Continuidad (m):",min_value=0.0,value=st.session_state.get("max_gap_dist",0.1),step=0.01,format="%.2f",key=f"num_gap_{APP_VERSION}",help="Si el gap entre tramos/bloques con mismo código supera esto, se consideran discontinuos.")
            st.session_state.max_iterations_reassign = st.number_input("Máx. iteraciones para Reasignación:",min_value=1,max_value=100,value=st.session_state.get("max_iterations_reassign",5),step=1,key=f"max_iter_reassign_f3_{APP_VERSION}")
            st.markdown("---") 

            if st.button("Continuar a Reasignación de Códigos (Fase 4)", key=f"btn_f3_to_f4_{APP_VERSION}"):
                if 'affinity_for_backend' not in st.session_state or st.session_state.affinity_for_backend.empty:
                    if not geocodes_activos_f3: st.error("No hay códigos activos para afinidad."); st.stop()
                    affinity_default_f3 = pd.DataFrame(True,index=geocodes_activos_f3,columns=geocodes_activos_f3,dtype=bool); np.fill_diagonal(affinity_default_f3.values,False)
                    st.session_state.affinity_for_backend = affinity_default_f3.copy(); st.info("Usando afinidad por defecto.")
                if st.session_state.df_original is None or st.session_state.equiv_final.empty or st.session_state.absorb_df.empty or not st.session_state.cols_sel:
                    st.error("Faltan datos/configuraciones."); st.stop()
                df_orig_f3 = st.session_state.df_original.copy(); equiv_final_f3 = st.session_state.equiv_final; cols_sel_f3 = st.session_state.cols_sel
                orig_geocode_col_f3 = cols_sel_f3["geocode_original"]; curated_geocode_col_f3 = cols_sel_f3["geocode_col_for_processing"]
                map_f3 = pd.Series(equiv_final_f3[curated_geocode_col_f3].values,index=equiv_final_f3[orig_geocode_col_f3].astype(str).str.strip().str.upper()).to_dict()
                df_orig_f3['map_key'] = df_orig_f3[orig_geocode_col_f3].astype(str).str.strip().str.upper()
                df_orig_f3[curated_geocode_col_f3] = df_orig_f3['map_key'].map(map_f3); df_orig_f3.drop(columns=['map_key'], inplace=True)
                
                # NO filtrar códigos ignorados aquí, se manejan en el backend
                # ignore_codes_f3 = equiv_final_f3[equiv_final_f3['ignorar'] == True][curated_geocode_col_f3].astype(str).unique()
                # active_df_f3 = df_orig_f3[~df_orig_f3[curated_geocode_col_f3].isin(ignore_codes_f3)].copy()
                active_df_f3 = df_orig_f3.copy() # Pasar todos los tramos con códigos curados

                process_codes_f3 = st.session_state.absorb_df['geocode'].astype(str).unique()
                # Filtrar para mantener solo los que tienen absorb_length definido O son ignorados y se manejarán especialmente
                # Si un código fue marcado como 'ignorar' en equiv_final, pero el usuario AÚN le definió un absorb_length
                # (porque no lo deseleccionó de los activos para absorb_df), se mantendrá.
                # La lógica de 'manejo_ignorados' en el backend se encargará de su comportamiento.
                active_df_f3 = active_df_f3[active_df_f3[curated_geocode_col_f3].isin(process_codes_f3) | \
                                            active_df_f3[curated_geocode_col_f3].isin(equiv_final_f3[equiv_final_f3['ignorar'] == True][curated_geocode_col_f3].astype(str).unique())
                                           ].reset_index(drop=True)
                
                from_c_f3, to_c_f3 = cols_sel_f3['from'], cols_sel_f3['to']
                try: active_df_f3[from_c_f3]=pd.to_numeric(active_df_f3[from_c_f3]); active_df_f3[to_c_f3]=pd.to_numeric(active_df_f3[to_c_f3])
                except ValueError: st.error(f"Columnas From/To no numéricas."); st.stop() 
                if active_df_f3.empty: st.error("No hay datos activos para procesar.")
                else:
                    st.session_state.df_active_for_processing = active_df_f3; st.session_state.fase = 4
                    st.session_state.df_block_reassigned_trace = None; st.session_state.diluted_df_simple_merge = None
                    st.success("Configuraciones guardadas."); st.rerun()
        st.markdown("---")

# --- FASE 4: Ejecución ---
if st.session_state.fase >= 4:
    if st.session_state.get('df_block_reassigned_trace') is None and st.session_state.fase == 4:
        with cont4:
            st.header("Fase 4: Ejecutando Dilución-reasignación de Códigos")
            if 'df_active_for_processing' not in st.session_state or st.session_state.df_active_for_processing is None or st.session_state.df_active_for_processing.empty:
                st.error("Faltan datos activos. Regresando a Fase 3."); st.session_state.fase = 3
                if st.button("Reintentar (Fase 3)", key=f"btn_retry_f4_{APP_VERSION}"): st.rerun()
                st.stop()
            st.info("Preparando parámetros...")
            max_iter_f4 = st.session_state.get("max_iterations_reassign", 10)
            act_bilateral_f4 = st.session_state.get("activar_absorcion_bilateral", False)
            multi_X_f4 = st.session_state.get("multiplicador_X_absorcion", 1.0)
            manejo_ign_f4 = st.session_state.get("manejo_ignorados", "A")
            max_gap_f4 = st.session_state.get("max_gap_dist", 0.1)
            
            codes_ign_list_f4 = []
            if st.session_state.equiv_final is not None and not st.session_state.equiv_final.empty:
                curated_col_ign_f4 = st.session_state.cols_sel["geocode_col_for_processing"]
                codes_ign_list_f4 = st.session_state.equiv_final[st.session_state.equiv_final['ignorar']==True][curated_col_ign_f4].astype(str).unique().tolist()

            absorb_lengths_f4 = dict(zip(st.session_state.absorb_df['geocode'].astype(str), st.session_state.absorb_df['absorb_length']))
            affinity_matrix_f4 = st.session_state.get('affinity_for_backend')
            if affinity_matrix_f4 is None or affinity_matrix_f4.empty: st.error("Matriz de afinidad no encontrada."); st.stop()
            
            cols_f4 = st.session_state.cols_sel
            hole_f4,from_f4,to_f4 = cols_f4['hole'],cols_f4['from'],cols_f4['to']
            geocode_curado_f4 = cols_f4["geocode_col_for_processing"]
            try:
                st.info(f"Iniciando reasignación (Bilateral:{act_bilateral_f4}, X:{multi_X_f4}, Ign:{manejo_ign_f4}, Gap:{max_gap_f4}, Iter:{max_iter_f4})...")
                input_df_f4 = st.session_state.df_active_for_processing.copy()
                default_abs_len_ign_f4 = st.session_state.get("default_absorb_length_setting", 0.01) 
                df_trace_res = generate_block_based_code_reassignment_trace(
                    input_df_f4, hole_f4, from_f4, to_f4, geocode_curado_f4,
                    absorb_lengths_f4, affinity_matrix_f4, act_bilateral_f4, multi_X_f4,
                    manejo_ign_f4, codes_ign_list_f4, max_gap_f4, default_abs_len_ign_f4, max_iter_f4)
                st.info("Función de reasignación completada.")
                if df_trace_res is not None:
                    st.session_state.df_block_reassigned_trace = df_trace_res
                    st.success("Proceso de reasignación finalizado.") 
                    st.info("Actualizando a Fase 5 para resultados...")
                    st.session_state.fase = 5; st.rerun()
                else: st.error("Reasignación no devolvió resultado."); st.session_state.fase = 3; st.rerun()
            except Exception as e: st.error(f"Error en reasignación: {e}"); st.exception(e); st.session_state.fase = 3; st.rerun()
    elif st.session_state.get('df_block_reassigned_trace') is not None and st.session_state.fase == 4:
        st.info("Fase 4 procesada, cargando Fase 5..."); st.session_state.fase = 5; st.rerun()

# --- FASE 5: Resultados ---
if st.session_state.fase >= 5:
    with cont5:
        st.header("Fase 5: Resultados del Procesamiento")
        cols_sel_f5 = st.session_state.cols_sel
        geocode_base_col_f5 = cols_sel_f5["geocode_col_for_processing"]
        from_col_f5, to_col_f5 = cols_sel_f5["from"], cols_sel_f5["to"]
        max_gap_dist_f5 = st.session_state.get("max_gap_dist", 0.1)

        st.subheader("5.1 Resultados de Reasignación de Códigos")
        df_trace_display_f5 = st.session_state.get('df_block_reassigned_trace')
        if df_trace_display_f5 is not None and not df_trace_display_f5.empty:
            st.write("**Trazabilidad (FROM-TO Originales con Códigos Reasignados):**")
            cols_show_trace_f5 = [cols_sel_f5['hole'], from_col_f5, to_col_f5]
            if geocode_base_col_f5 in df_trace_display_f5.columns: cols_show_trace_f5.append(geocode_base_col_f5)
            else: cols_show_trace_f5.append(cols_sel_f5['geocode_original'])
            if st.session_state.df_active_for_processing is not None:
                other_orig_cols_f5 = [c for c in st.session_state.df_active_for_processing.columns if c not in cols_show_trace_f5 and c in df_trace_display_f5.columns]
                cols_show_trace_f5.extend(other_orig_cols_f5)
            export_all_iters_f5 = st.checkbox("Mostrar todas las cols. de iteración", value=False, key=f"cb_all_iters_f5_{APP_VERSION}")
            display_cols_f5 = list(cols_show_trace_f5)
            iter_cols_names_f5 = sorted([c for c in df_trace_display_f5.columns if c.startswith('geocode_iter_') and c!='geocode_iter_final'])
            if export_all_iters_f5: display_cols_f5.extend(iter_cols_names_f5)
            if 'geocode_iter_final' in df_trace_display_f5.columns: display_cols_f5.append('geocode_iter_final')
            display_cols_f5 = list(dict.fromkeys(c for c in display_cols_f5 if c in df_trace_display_f5.columns))
            st.dataframe(df_trace_display_f5[display_cols_f5].head(10))
            try:
                csv_trace_f5 = df_trace_display_f5[display_cols_f5].to_csv(index=False).encode('utf-8')
                st.download_button("Descargar CSV - Trazabilidad", csv_trace_f5, "trazabilidad.csv", "text/csv", key=f"dl_trace_f5_{APP_VERSION}")
            except Exception as e: st.error(f"Error CSV Trazabilidad: {e}")

            st.markdown("---"); st.write("**Matriz de Cambio (Curado vs. Final Reasignado):**")
            if geocode_base_col_f5 in df_trace_display_f5.columns and 'geocode_iter_final' in df_trace_display_f5.columns:
                matrix_f5 = calculate_change_matrix(df_trace_display_f5, geocode_base_col_f5,'geocode_iter_final',from_col_f5,to_col_f5)
                st.dataframe(matrix_f5)
            else: st.warning(f"Columnas para matriz no disponibles.")
            st.markdown("---"); st.write("**Metros Acumulados de Cambio (Reasignación):**")
            cum_df_f5 = calculate_cumulative_change_per_iteration(df_trace_display_f5,geocode_base_col_f5,from_col_f5,to_col_f5)
            if not cum_df_f5.empty: st.line_chart(cum_df_f5.set_index('Iteración'))
            else: st.info("No hay datos para gráfico de cambio acumulado.")
        else: st.info("No se generaron resultados de reasignación de códigos.")
        st.markdown("---")

        st.subheader("5.2 Intervalos Diluidos (Fusión Simple de tramos (from-to) finales reasignados)")
        if st.session_state.get('diluted_df_simple_merge') is None and df_trace_display_f5 is not None and \
           'geocode_iter_final' in df_trace_display_f5.columns and not df_trace_display_f5.empty:
            st.info(f"Generando fusión simple (Max Gap: {max_gap_dist_f5}m)...")
            other_cols_merge_f5 = [c for c in df_trace_display_f5.columns if c not in [cols_sel_f5['hole'],from_col_f5,to_col_f5,'geocode_iter_final'] and not c.startswith('geocode_iter_')]
            if geocode_base_col_f5 not in other_cols_merge_f5 and geocode_base_col_f5 in df_trace_display_f5.columns: other_cols_merge_f5.append(geocode_base_col_f5)
            st.session_state.diluted_df_simple_merge = merge_final_block_codes(df_trace_display_f5,cols_sel_f5['hole'],from_col_f5,to_col_f5,'geocode_iter_final',[],max_gap_dist_f5)
            st.rerun() 
        df_simple_merged_f5 = st.session_state.get('diluted_df_simple_merge')
        if df_simple_merged_f5 is not None and not df_simple_merged_f5.empty:
            st.dataframe(df_simple_merged_f5.head(10))
            try:
                csv_simple_merged_f5 = df_simple_merged_f5.to_csv(index=False).encode('utf-8')
                st.download_button("Descargar CSV - Fusión Simple", csv_simple_merged_f5,"intervalos_diluidos_simple.csv","text/csv",key=f"dl_simple_f5_{APP_VERSION}")
            except Exception as e: st.error(f"Error CSV fusión simple: {e}")
        elif df_simple_merged_f5 is not None: st.info("Fusión simple no generó intervalos.")
        else: st.info("Pendiente de generar fusión simple.")
        st.markdown("---")
        
        st.subheader("5.3 Análisis de Proporciones de Geocódigos")
        df_prop_antes_f5 = st.session_state.get('df_active_for_processing')
        df_prop_despues_f5 = st.session_state.get('diluted_df_simple_merge')
        if df_prop_antes_f5 is not None and not df_prop_antes_f5.empty and df_prop_despues_f5 is not None:
            geocode_col_merged_f5 = 'geocode_iter_final'.replace('_iter_final','') if '_iter_final' in 'geocode_iter_final' else 'geocode'
            if (not df_prop_despues_f5.empty and geocode_col_merged_f5 not in df_prop_despues_f5.columns):
                st.warning(f"Columna '{geocode_col_merged_f5}' no en fusión para proporciones."); df_prop_despues_f5 = pd.DataFrame() 
            c1_props_f5, c2_props_f5 = st.columns(2)
            with c1_props_f5:
                st.write("**Comparación (Original Curado vs. Fusión Simple Final):**")
                props_antes = calculate_geocode_proportions(df_prop_antes_f5,geocode_base_col_f5,from_col_f5,to_col_f5).rename(columns={geocode_base_col_f5:'Geocódigo','total_length':'Metros Antes','proportion_str':'% Antes'})[['Geocódigo','Metros Antes','% Antes']]
                if not df_prop_despues_f5.empty:
                    props_despues = calculate_geocode_proportions(df_prop_despues_f5,geocode_col_merged_f5,from_col_f5,to_col_f5).rename(columns={geocode_col_merged_f5:'Geocódigo','total_length':'Metros Después','proportion_str':'% Después'})[['Geocódigo','Metros Después','% Después']]
                else: props_despues = pd.DataFrame({'Geocódigo':props_antes['Geocódigo'].unique(),'Metros Después':0.0,'% Después':'0.00%'})
                merged_props_f5 = pd.merge(props_antes,props_despues,on='Geocódigo',how='outer').fillna(0)
                merged_props_f5['Metros Antes']=merged_props_f5['Metros Antes'].round(2); merged_props_f5['Metros Después']=merged_props_f5['Metros Después'].round(2)
                for col_p in ['% Antes','% Después']:
                    if col_p in merged_props_f5: merged_props_f5[col_p]=merged_props_f5[col_p].apply(lambda x:x if isinstance(x,str)and'%'in x else(f"{float(x):.2f}%"if pd.notnull(x)and x!=0 else"0.00%"))
                st.dataframe(merged_props_f5[['Geocódigo','Metros Antes','% Antes','Metros Después','% Después']])
            with c2_props_f5:
                st.write("**Gráfico de Cambio en Metros:**")
                if not merged_props_f5.empty:
                    chart_df_f5 = merged_props_f5.copy(); chart_df_f5['Cambio Metros']=chart_df_f5['Metros Después']-chart_df_f5['Metros Antes']
                    chart_df_plot_f5 = chart_df_f5.set_index('Geocódigo')[['Cambio Metros']].sort_values(by='Cambio Metros',ascending=False)
                    if not chart_df_plot_f5.empty: st.bar_chart(chart_df_plot_f5)
                    else: st.info("No hay datos para gráfico cambio.")
                else: st.info("No hay datos para gráfico cambio.")
        else: st.info("No hay suficientes datos para análisis de proporciones.")
        st.markdown("---")

# --- Sidebar ---
st.sidebar.info(f"Versión: {APP_VERSION}")
st.sidebar.markdown("""**Guía Rápida:**
1.  F0: Carga y Selección de columnas dhid, desde, hasta y geocódigo.
2.  F1: Curado Códigos. Selecciona códigos a ignorar.
3.  F2: `absorb_length` tamaño máximo para considerar un tramo como absorbible. Ignorados usan defecto
4.  F3-Afinandad: Afinidad todos los códigos pueden ser absorbidos por otros. Excepciones indican dado un código quienes NO pueden absorberlo
5.  F3-Tipo: Bilateral: se absorben solo si tramo esta rodeado por mismo código. Inactivo unilateral. Gana el más largo
6.  F3-Manejo Ignorados: A: Ignorados no cambian ni absorben. B: Ignorados pueden ser absorbidos por no-ignorados, pero no absorben. Largo defecto.                   
7.  F4: Ejecutar Reasignación - Dilución
8.  F5: Resultados (Fusión Simple Final)
9.  F5: Setear navegador para guardar no solo en descargas.                    
                    """)
