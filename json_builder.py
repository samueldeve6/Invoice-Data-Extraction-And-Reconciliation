"""
json_builder.py
Generación de JSON final. Maneja NaN / NaT y calcula métricas.
"""
import json
from datetime import datetime
import math
import numpy as np
import pandas as pd

def sanitize_for_json(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj

def clean_dataframe_for_json(df):
    # reemplazar NaN por None y convertir timestamps a str
    df = df.copy()
    df = df.replace({np.nan: None})
    
    # Asegurar que las columnas de fechas siempre existan (incluso si están vacías)
    if 'fecha_inicio' not in df.columns:
        df['fecha_inicio'] = None
    if 'fecha_final' not in df.columns:
        df['fecha_final'] = None
        
    # Convertir valores vacíos a None para consistencia
    df['fecha_inicio'] = df['fecha_inicio'].replace('', None)
    df['fecha_final'] = df['fecha_final'].replace('', None)
    
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].apply(lambda x: x.isoformat() if x is not None else None)
    return df

def build_json(df, output_path, errores, total_pdf, total_excel, resultados_conciliacion):
    df_clean = clean_dataframe_for_json(df)

    proveedores_pdf = len([r for r in resultados_conciliacion if r.get('estado') != 'SOLO_EXCEL'])
    proveedores_excel = len([r for r in resultados_conciliacion if r.get('estado') != 'SOLO_PDF'])

    resultados_conciliacion = sanitize_for_json(resultados_conciliacion)
    errores = sanitize_for_json(errores)

    # detectar columna total excel
    excel_total_col = None
    for c in df_clean.columns:
        if "TOTAL A PAGAR" in str(c).upper():
            excel_total_col = c
            break
    if excel_total_col is None:
        for c in df_clean.columns:
            if "AMOUNT TOTAL" in str(c).upper() or "AMOUNT" in str(c).upper():
                excel_total_col = c
                break
    if excel_total_col is None:
        excel_total_col = "Subtotal" if "Subtotal" in df_clean.columns else "total_excel"
    
    # --- MÉTRICAS GLOBALES ---
    total_proveedores_match = len([r for r in resultados_conciliacion if r['estado'] == 'COINCIDEN'])
    total_proveedores_difieren = len([r for r in resultados_conciliacion if r['estado'] == 'DIFIEREN'])
    total_solo_pdf = len([r for r in resultados_conciliacion if r['estado'] == 'SOLO_PDF'])
    total_solo_excel = len([r for r in resultados_conciliacion if r['estado'] == 'SOLO_EXCEL'])
    
    # Calcular totales monetarios
    total_monto_pdf = df_clean['total_pdf'].sum() if 'total_pdf' in df_clean.columns else 0
    total_monto_excel = df_clean[excel_total_col].sum() if excel_total_col in df_clean.columns else 0
    
    # Top 5 discrepancias (mayor diferencia porcentual)
    discrepancias_ordenadas = sorted(
        [r for r in resultados_conciliacion if r['diferencia_porcentual'] > 0],
        key=lambda x: x['diferencia_porcentual'],
        reverse=True
    )[:5]
    
    # --- ESTRUCTURA JSON SEGÚN PRUEBA TÉCNICA ---
    json_output = {
        "metadata": {
            "fecha_generacion": pd.Timestamp.now().isoformat(),
            "herramientas": ["Python", "pandas", "pdfplumber", "openpyxl"],
            "totales_fuentes": {
                "facturas_pdf": total_pdf,
                "facturas_excel": total_excel,
                "proveedores_pdf": proveedores_pdf,
                "proveedores_excel": proveedores_excel
            }
        },
        "proveedores": resultados_conciliacion,
        "resumen_conciliacion": {
            "metricas_globales": {
                "proveedores_match": total_proveedores_match,
                "proveedores_difieren": total_proveedores_difieren,
                "solo_pdf": total_solo_pdf,
                "solo_excel": total_solo_excel,
                "total_proveedores": len(resultados_conciliacion),
                "porcentaje_coincidencia": round((total_proveedores_match / len(resultados_conciliacion)) * 100, 2) if resultados_conciliacion else 0
            },
            "montos_totales": {
                "total_pdf": round(total_monto_pdf, 2),
                "total_excel": round(total_monto_excel, 2),
                "diferencia_absoluta": round(abs(total_monto_pdf - total_monto_excel), 2),
                "diferencia_porcentual": round((abs(total_monto_pdf - total_monto_excel) / max(total_monto_pdf, total_monto_excel, 1)) * 100, 2)
            },
            "top_5_discrepancias": [
                {
                    "nit": d["nit"],
                    "nombre_proveedor": d["nombre_proveedor"],
                    "diferencia_porcentual": round(d["diferencia_porcentual"], 2),
                    "diferencia_absoluta": round(d["diferencia_absoluta"], 2),
                    "total_pdf": round(d["total_pdf"], 2),
                    "total_excel": round(d["total_excel"], 2),
                    "diferencias_detalle": d["diferencias"]
                }
                for d in discrepancias_ordenadas
            ],
            "hallazgos_y_recomendaciones": {
                "resumen_ejecutivo": f"Se procesaron {total_pdf} facturas PDF y {total_excel} registros Excel. Se encontraron {total_proveedores_match} proveedores con coincidencias ({round((total_proveedores_match / len(resultados_conciliacion)) * 100, 1)}%), {total_proveedores_difieren} con diferencias y {total_solo_pdf + total_solo_excel} proveedores que aparecen en una sola fuente.",
                "principales_hallazgos": [
                    f"{total_solo_pdf} proveedores están en PDFs pero no en AP Listing",
                    f"{total_solo_excel} proveedores están en AP Listing pero no en PDFs",
                    f"Diferencia total de montos: ${abs(total_monto_pdf - total_monto_excel):,.2f}"
                ],
                "recomendaciones": [
                    "Verificar proveedores que aparecen solo en PDFs",
                    "Revisar facturas con diferencias de montos > 5%",
                    "Actualizar AP Listing con proveedores faltantes",
                    "Estandarizar formatos de NIT en ambas fuentes"
                ]
            }
        },
        "datos_detallados": {
            "registros_conciliados": df_clean[
                [
                    c for c in [
                        'source_file',
                        'nit_normalized',
                        'nombre_proveedor_pdf',
                        'numero_factura_pdf',
                        'invoice_id_normalized',
                        'fecha_inicio',
                        'fecha_final',
                        'moneda_pdf',
                        'subtotal_pdf',
                        'iva_porcentaje',
                        'iva_monto',
                        'total_pdf',
                        'orden_compra',
                        'cufe',
                        'tipo_factura',
                        # Campos clave Excel (según prueba)
                        'nombre_proveedor_excel',  # Supplier/Beneficiary Name
                        'numero_factura_excel',    # Invoice ID
                        'NIT',
                        'excel_invoice_date',      # Invoice Date
                        'subtotal_excel',          # Subtotal
                        'VAT/WHT1',                # IVA (si aplica)
                        'total_excel',
                        'excel_curr.',
                        'PO #',
                        'Spend Category',
                        'Cost Center',
                        'Location',
                        'estado_conciliacion',
                    ] if c in df_clean.columns
                ]
            ].to_dict('records')
        },
        "errores_y_excepciones": {
            "pdfs_procesados": total_pdf,
            "pdfs_con_error": len(errores),
            "detalles_errores": errores[:10]  # Limitar a primeros 10 errores
        }
    }
    
    # Guardar JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"✅ JSON guardado en: {output_path}")
    print(f"📊 Resumen: {total_proveedores_match} coincidencias, {total_proveedores_difieren} diferencias, {total_solo_pdf} solo PDF, {total_solo_excel} solo Excel")
