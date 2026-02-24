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
    for col in ['subtotal', 'iva_monto', 'total', 'otros_impuestos']:
        if col in pdf_df.columns:
            pdf_df[col] = pd.to_numeric(pdf_df[col], errors='coerce').fillna(0).round(2)
    
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
        
        # Comparar facturas
        pdf_facturas = set(pdf_proveedor['invoice_id_normalized'].dropna())
        if 'invoice_id_normalized' in excel_proveedor.columns:
            excel_facturas = set(excel_proveedor['invoice_id_normalized'].dropna())
        else:
            excel_facturas = set(excel_proveedor.get('Invoice ID', pd.Series(dtype=object)).dropna())
        facturas_comunes = pdf_facturas & excel_facturas
        
        # Comparar montos: calcular subtotal, IVA y total con redondeo consistente
        subtotal_pdf = round(pdf_proveedor['subtotal'].sum() if 'subtotal' in pdf_proveedor.columns else 0, 2)
        iva_pdf = round(pdf_proveedor['iva_monto'].sum() if 'iva_monto' in pdf_proveedor.columns else 0, 2)
        # Preferimos la columna 'total' si está disponible, sino sumamos subtotal+iva
        total_pdf_val = round(pdf_proveedor['total'].sum() if 'total' in pdf_proveedor.columns else (subtotal_pdf + iva_pdf), 2)

        subtotal_excel = round(excel_proveedor['Subtotal'].sum() if 'Subtotal' in excel_proveedor.columns else 0, 2)
        iva_excel = round(excel_proveedor['VAT/WHT1'].sum() if 'VAT/WHT1' in excel_proveedor.columns else 0, 2)
        total_excel_val = round(excel_proveedor['Amount Total'].sum() if 'Amount Total' in excel_proveedor.columns else (subtotal_excel + iva_excel), 2)

        diferencia_abs = round(abs(total_pdf_val - total_excel_val), 2)
        diferencia_pct = round((diferencia_abs / max(total_pdf_val, total_excel_val, 1)) * 100, 2)

        # Clasificar coincidencia
        TOLERANCIA = 1  # 1 peso
        if (len(facturas_comunes) > 0 and diferencia_abs <= TOLERANCIA):
            estado = "COINCIDEN"
        else:
            estado = "DIFIEREN"

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
            "subtotal_pdf": subtotal_pdf,
            "iva_pdf": iva_pdf,
            "total_pdf": total_pdf_val,
            "subtotal_excel": subtotal_excel,
            "iva_excel": iva_excel,
            "total_excel": total_excel_val,
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
        # PROVEEDOR SOLO EN PDF: incluir llaves `subtotal_pdf` y `total_pdf` de forma consistente
        resultado = {
            "nit": nit,
            "nombre_proveedor": pdf_proveedor['nombre_proveedor'].iloc[0],
            "estado": "SOLO_PDF",
            "nombre_coincide": False,
            "facturas_pdf": len(pdf_proveedor),
            "facturas_excel": 0,
            "facturas_comunes": 0,
            "subtotal_pdf": round(pdf_proveedor['subtotal'].sum() if 'subtotal' in pdf_proveedor.columns else 0, 2),
            "iva_pdf": round(pdf_proveedor['iva_monto'].sum() if 'iva_monto' in pdf_proveedor.columns else 0, 2),
            "total_pdf": round(pdf_proveedor['total'].sum() if 'total' in pdf_proveedor.columns else pdf_proveedor['subtotal'].sum(), 2),
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
        # PROVEEDOR SOLO EN EXCEL: incluir `total_excel` y `subtotal_excel` de forma consistente
        resultado = {
            "nit": nit,
            "nombre_proveedor": excel_proveedor['Supplier/Beneficiary Name'].iloc[0],
            "estado": "SOLO_EXCEL",
            "nombre_coincide": False,
            "facturas_pdf": 0,
            "facturas_excel": len(excel_proveedor),
            "facturas_comunes": 0,
            "subtotal_pdf": 0,
            "iva_pdf": 0,
            "total_pdf": 0,
            "subtotal_excel": round(excel_proveedor['Subtotal'].sum() if 'Subtotal' in excel_proveedor.columns else 0, 2),
            "iva_excel": round(excel_proveedor['VAT/WHT1'].sum() if 'VAT/WHT1' in excel_proveedor.columns else 0, 2),
            "total_excel": round(excel_proveedor['Amount Total'].sum() if 'Amount Total' in excel_proveedor.columns else excel_proveedor['Subtotal'].sum(), 2),
            "diferencia_absoluta": 0,
            "diferencia_porcentual": 0,
            "diferencias": ["Proveedor no encontrado en facturas PDF"],
            "facturas_pdf_detalle": [],
            "facturas_excel_detalle": excel_proveedor.to_dict('records')
        }
        resultados.append(resultado)
    
    # --- MERGE FINAL PARA EL JSON ---
    
    # 1. Asegurar identificadores en Excel para el Merge
    if 'invoice_id_normalized' not in excel_df.columns:
        col_f = 'Invoice ID' if 'Invoice ID' in excel_df.columns else 'NIT'
        excel_df['invoice_id_normalized'] = excel_df[col_f].astype(str).str.strip()

    # 2. AGRUPAR EXCEL (Usamos nombres originales para evitar KeyError)
    # Agregamos los campos que necesitas en el JSON final
    excel_df_grouped = excel_df.groupby(['nit_normalized', 'invoice_id_normalized'], as_index=False).agg({
        'Subtotal': 'sum',
        'Amount Total': 'sum',
        'VAT/WHT1': 'sum',
        'Supplier/Beneficiary Name': 'first',
        'Curr.': 'first',
        'Invoice Date': 'first' if 'Invoice Date' in excel_df.columns else 'first'
    })

    # 3. MERGE PRINCIPAL
    merged = pd.merge(
        pdf_df,
        excel_df_grouped,
        on=['nit_normalized', 'invoice_id_normalized'],
        how='left'
    )

    # 4. RENOMBRAR PARA EL JSON FINAL
    columnas_renombrar = {
        'nombre_proveedor': 'nombre_proveedor_pdf',
        'Supplier/Beneficiary Name': 'nombre_proveedor_excel',
        'numero_factura': 'numero_factura_pdf', 
        'invoice_id_normalized': 'numero_factura_excel',
        'total': 'total_pdf',
        'Amount Total': 'total_excel',
        'subtotal': 'subtotal_pdf',
        'Subtotal': 'subtotal_excel',
        'moneda': 'moneda_pdf',
        'Curr.': 'moneda_excel',
        'Invoice Date': 'fecha_excel'
    }
    
    # Renombrar solo las columnas que realmente terminaron en el DataFrame merged
    merged = merged.rename(columns={k: v for k, v in columnas_renombrar.items() if k in merged.columns})

    # 5. ASIGNAR ESTADO
    estado_map = {r['nit']: r['estado'] for r in resultados}
    merged['estado_conciliacion'] = merged['nit_normalized'].map(estado_map)
    
    print(f"DEBUG - Resultados de conciliación: {len(resultados)} proveedores")
    print(f"DEBUG - Merge final: {len(merged)} registros")
    
    return merged, resultados