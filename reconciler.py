"""
reconciler.py
Hace reconciliación en dos pasos:
- Merge exacto por (nit_normalized, invoice id)
- Merge por nit_normalized (fallback) para detectar coincidencias por NIT aunque invoice difiera
Calcula diferencias y clasifica filas.
"""
import pandas as pd
import numpy as np

def clean_nit(nit):
    """Limpiar NIT eliminando caracteres no numéricos y dígito de verificación"""
    nit = str(nit) if pd.notna(nit) else ''
    nit = ''.join(c for c in nit if c.isdigit())
    # Eliminar dígito de verificación si tiene más de 9 dígitos
    if len(nit) > 9:
        nit = nit[:9]
    return nit

def normalize_supplier_name(name):
    """Normalizar nombre de proveedor para comparación flexible"""
    if pd.isna(name):
        return ''
    name = str(name).upper()
    # Eliminar solo caracteres especiales, mantener palabras importantes
    # Solo eliminar sufijos legales comunes
    suffixes_to_remove = [' LTDA', ' SAS', ' S.A.', ' S.A', ' SA']
    for suffix in suffixes_to_remove:
        name = name.replace(suffix, '')
    # Solo dejar letras, números y espacios
    name = ''.join(c for c in name if c.isalnum() or c.isspace())
    return name.strip()

def reconcile(pdf_df, excel_df):
    """
    Realiza conciliación completa entre PDFs y AP Listing
    Retorna: (merged_df, resultados_conciliacion)
    """
    # Normalizar NITs con función mejorada
    pdf_df['nit_normalized'] = pdf_df['nit_proveedor'].apply(clean_nit)
    excel_df['nit_normalized'] = excel_df['NIT'].apply(clean_nit)
    
    # Normalizar nombres de proveedores con función flexible
    pdf_df['supplier_normalized'] = pdf_df['nombre_proveedor'].apply(normalize_supplier_name)
    excel_df['supplier_normalized'] = excel_df['Supplier/Beneficiary Name'].apply(normalize_supplier_name)
    
    # Normalizar montos a numérico
    for col in ['subtotal', 'iva_monto', 'total']:
        if col in pdf_df.columns:
            pdf_df[col] = pd.to_numeric(pdf_df[col], errors='coerce')
    
    for col in ['Subtotal', 'VAT/WHT1', 'Amount Total']:
        if col in excel_df.columns:
            excel_df[col] = pd.to_numeric(excel_df[col], errors='coerce')
    
    print(f"DEBUG - PDF NIT únicos: {pdf_df['nit_normalized'].unique()}")
    print(f"DEBUG - Excel NIT únicos: {excel_df['nit_normalized'].unique()}")
    
    # --- ANÁLISIS DE COINCIDENCIAS ---
    resultados = []
    
    # 1. Encontrar proveedores que están en ambas fuentes (MATCH)
    nits_comunes = set(pdf_df['nit_normalized'].dropna()) & set(excel_df['nit_normalized'].dropna())
    print(f"DEBUG - NITS comunes: {len(nits_comunes)}")
    
    # 2. Proveedores solo en PDF
    nits_solo_pdf = set(pdf_df['nit_normalized'].dropna()) - set(excel_df['nit_normalized'].dropna())
    
    # 3. Proveedores solo en Excel
    nits_solo_excel = set(excel_df['nit_normalized'].dropna()) - set(pdf_df['nit_normalized'].dropna())
    
    print(f"DEBUG - Resumen: {len(nits_comunes)} match, {len(nits_solo_pdf)} solo PDF, {len(nits_solo_excel)} solo Excel")
    
    # --- ANÁLISIS DETALLADO DE NITs PARA DEBUG ---
    print("\n🔍 ANÁLISIS DETALLADO DE NITs:")
    print(f"NITs PDF: {sorted(pdf_df['nit_normalized'].unique())}")
    print(f"NITs Excel: {sorted(excel_df['nit_normalized'].unique())}")
    print(f"NITs comunes: {sorted(nits_comunes)}")
    
    # Analizar NITs similares que podrían coincidir
    for nit_pdf in sorted(pdf_df['nit_normalized'].unique()):
        for nit_excel in sorted(excel_df['nit_normalized'].unique()):
            if nit_pdf and nit_excel:
                # Si son similares pero no idénticos
                if nit_pdf[:8] == nit_excel[:8] and nit_pdf != nit_excel:
                    print(f"⚠️ NITs similares pero diferentes: PDF={nit_pdf} vs Excel={nit_excel}")
    
    # --- PROCESAR PROVEEDORES CON COINCIDENCIA ---
    for nit in nits_comunes:
        pdf_proveedor = pdf_df[pdf_df['nit_normalized'] == nit]
        excel_proveedor = excel_df[excel_df['nit_normalized'] == nit]
        
        # Comparar nombres
        pdf_nombre = pdf_proveedor['supplier_normalized'].iloc[0] if not pdf_proveedor.empty else ''
        excel_nombre = excel_proveedor['supplier_normalized'].iloc[0] if not excel_proveedor.empty else ''
        
        nombre_coincide = pdf_nombre == excel_nombre
        
        # Comparar facturas (usar IDs normalizados para evitar fallos por formato: '59208.0', espacios, etc.)
        pdf_facturas = set(pdf_proveedor['invoice_id_normalized'].dropna())
        if 'invoice_id_normalized' in excel_proveedor.columns:
            excel_facturas = set(excel_proveedor['invoice_id_normalized'].dropna())
        else:
            excel_facturas = set(excel_proveedor.get('Invoice ID', pd.Series(dtype=object)).dropna())
        facturas_comunes = pdf_facturas & excel_facturas
        
        # Comparar montos subtotal
        subtotal_pdf = pdf_proveedor['subtotal'].sum() if 'subtotal' in pdf_proveedor.columns else 0
        subtotal_excel = excel_proveedor['Subtotal'].sum() if 'Subtotal' in excel_proveedor.columns else 0

        diferencia_abs = abs(subtotal_pdf - subtotal_excel)
        diferencia_pct = (diferencia_abs / max(subtotal_pdf, subtotal_excel, 1)) * 100

        iva_pdf = pdf_proveedor['iva_monto'].sum() if 'iva_monto' in pdf_proveedor.columns else 0
        iva_excel = excel_proveedor['VAT/WHT1'].sum() if 'VAT/WHT1' in excel_proveedor.columns else 0

        iva_diff = abs(iva_pdf - iva_excel)
        # Clasificar coincidencia con criterios más flexibles
        TOLERANCIA = 1  # 1 peso

        if (
            len(facturas_comunes) > 0
            and abs(subtotal_pdf - subtotal_excel) <= TOLERANCIA
        ):
            estado = "COINCIDEN"
        else:
            estado = "DIFIEREN"

                # Detalles de diferencias
        diferencias = []
        if not nombre_coincide:
            diferencias.append(f"Nombres: PDF='{pdf_proveedor['nombre_proveedor'].iloc[0]}' vs Excel='{excel_proveedor['Supplier/Beneficiary Name'].iloc[0]}'")
        
        if len(facturas_comunes) == 0:
            diferencias.append(f"Sin facturas coincidentes: PDF={len(pdf_facturas)} vs Excel={len(excel_facturas)}")
        
        if diferencia_pct > 5:
            diferencias.append(f"Montos: PDF=${subtotal_pdf:,.2f} vs Excel=${subtotal_excel:,.2f} (diferencia {diferencia_pct:.1f}%)")
        
        resultado = {
            "nit": nit,
            "nombre_proveedor": pdf_proveedor['nombre_proveedor'].iloc[0] if not pdf_proveedor.empty else excel_proveedor['Supplier/Beneficiary Name'].iloc[0],
            "estado": estado,
            "nombre_coincide": nombre_coincide,
            "facturas_pdf": len(pdf_facturas),
            "facturas_excel": len(excel_facturas),
            "facturas_comunes": len(facturas_comunes),
            "total_pdf": subtotal_pdf,
            "total_excel": subtotal_excel,
            "diferencia_absoluta": diferencia_abs,
            "diferencia_porcentual": diferencia_pct,
            "diferencias": diferencias,
            "facturas_pdf_detalle": pdf_proveedor.to_dict('records') if not pdf_proveedor.empty else [],
            "facturas_excel_detalle": excel_proveedor.to_dict('records') if not excel_proveedor.empty else []
        }
        
        resultados.append(resultado)
    
    # --- PROVEEDORES SOLO EN PDF ---
    for nit in nits_solo_pdf:
        pdf_proveedor = pdf_df[pdf_df['nit_normalized'] == nit]
        
        resultado = {
            "nit": nit,
            "nombre_proveedor": pdf_proveedor['nombre_proveedor'].iloc[0],
            "estado": "SOLO_PDF",
            "nombre_coincide": False,
            "facturas_pdf": len(pdf_proveedor),
            "facturas_excel": 0,
            "facturas_comunes": 0,
            "subtotal_pdf": pdf_proveedor['subtotal'].sum() if 'subtotal' in pdf_proveedor.columns else 0,
            "subtotal_excel": 0,
            "diferencia_absoluta": 0,
            "diferencia_porcentual": 0,
            "diferencias": ["Proveedor no encontrado en AP Listing"],
            "facturas_pdf_detalle": pdf_proveedor.to_dict('records'),
            "facturas_excel_detalle": []
        }
        
        resultados.append(resultado)
    
    # --- PROVEEDORES SOLO EN EXCEL ---
    for nit in nits_solo_excel:
        excel_proveedor = excel_df[excel_df['nit_normalized'] == nit]
        
        resultado = {
            "nit": nit,
            "nombre_proveedor": excel_proveedor['Supplier/Beneficiary Name'].iloc[0],
            "estado": "SOLO_EXCEL",
            "nombre_coincide": False,
            "facturas_pdf": 0,
            "facturas_excel": len(excel_proveedor),
            "facturas_comunes": 0,
            "subtotal_pdf": 0,
            "subtotal_excel": excel_proveedor['Subtotal'].sum() if 'Subtotal' in excel_proveedor.columns else 0,
            "diferencia_absoluta": 0,
            "diferencia_porcentual": 0,
            "diferencias": ["Proveedor no encontrado en facturas PDF"],
            "facturas_pdf_detalle": [],
            "facturas_excel_detalle": excel_proveedor.to_dict('records')
        }
        
        resultados.append(resultado)
    
    # --- MERGE FINAL PARA EL JSON ---
    # Guardar las fechas del PDF antes del merge
    pdf_dates = pdf_df[['invoice_id_normalized', 'fecha_inicio', 'fecha_final']].copy()
    
    # Renombrar columnas del Excel para evitar conflictos
    excel_renamed = excel_df.copy()
    excel_cols_conflict = ['Request Date', 'Invoice Date', 'Due Date', 'Curr.', 'invoice_date_normalized']
    for col in excel_cols_conflict:
        if col in excel_renamed.columns:
            excel_renamed = excel_renamed.rename(columns={col: f"excel_{col.lower().replace(' ', '_')}"})
    
    # Merge principal - LEFT JOIN por NIT + Invoice ID (evita duplicación masiva)
    if 'invoice_id_normalized' not in excel_renamed.columns:
        excel_renamed['invoice_id_normalized'] = None
    merged = pd.merge(
        pdf_df,
        excel_renamed,
        on=['nit_normalized', 'invoice_id_normalized'],
        how='left',
        suffixes=('_pdf', '_excel')
    )
    
    # Restaurar fechas del PDF - usar la columna correcta después del merge
    invoice_col = 'invoice_id_normalized_pdf' if 'invoice_id_normalized_pdf' in merged.columns else 'invoice_id_normalized'
    
    for _, row in pdf_dates.iterrows():
        mask = merged[invoice_col] == row['invoice_id_normalized']
        merged.loc[mask, 'fecha_inicio'] = row['fecha_inicio']
        merged.loc[mask, 'fecha_final'] = row['fecha_final']
    
    # Asegurar que invoice_id_normalized exista (priorizar PDF si existe)
    if 'invoice_id_normalized_pdf' in merged.columns:
        merged['invoice_id_normalized'] = merged['invoice_id_normalized_pdf'].fillna(merged.get('invoice_id_normalized_excel', ''))
    elif 'invoice_id_normalized_excel' in merged.columns:
        merged['invoice_id_normalized'] = merged['invoice_id_normalized_excel']
    
    # Limpiar columnas conflictivas
    for col in ['fecha_inicio', 'fecha_final']:
        for suffix in ['_pdf', '_excel', '']:
            full_col = f"{col}{suffix}"
            if full_col in merged.columns and full_col != col:
                merged = merged.drop(full_col, axis=1, errors='ignore')
    
    # Renombrar columnas para claridad
    columnas_renombrar = {
        'nombre_proveedor': 'nombre_proveedor_pdf',
        'Supplier/Beneficiary Name': 'nombre_proveedor_excel',
        'numero_factura': 'numero_factura_pdf', 
        'Invoice ID': 'numero_factura_excel',
        'total': 'total_pdf',
        'Amount Total': 'total_excel',
        'subtotal': 'subtotal_pdf',
        'Subtotal': 'subtotal_excel',
        'moneda': 'moneda_pdf',
        'Curr.': 'moneda_excel'
    }
    
    for old_col, new_col in columnas_renombrar.items():
        if old_col in merged.columns:
            merged = merged.rename(columns={old_col: new_col})
    
    # Añadir información de conciliación al merged
    merged['estado_conciliacion'] = merged['nit_normalized'].map(
        {r['nit']: r['estado'] for r in resultados}
    )
    
    print(f"DEBUG - Resultados de conciliación: {len(resultados)} proveedores procesados")
    print(f"DEBUG - Merge final: {len(merged)} registros")
    
    return merged, resultados