"""
json_builder.py
Generación de JSON final. Maneja NaN / NaT y calcula métricas.
"""
import json
from datetime import datetime
import numpy as np
import pandas as pd

def clean_dataframe_for_json(df):
    # reemplazar NaN por None y convertir timestamps a str
    df = df.copy()
    df = df.replace({np.nan: None})
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].apply(lambda x: x.isoformat() if x is not None else None)
    return df

def build_json(df, output_path, errores, total_pdf, total_excel):
    df_clean = clean_dataframe_for_json(df)

    # detectar columna total excel
    excel_total_col = None
    for c in df_clean.columns:
        if c and "TOTAL A PAGAR" in str(c).upper():
            excel_total_col = c
            break
    if excel_total_col is None:
        for c in df_clean.columns:
            if c and ("AMOUNT TOTAL" in str(c).upper() or "AMOUNT" in str(c).upper()):
                excel_total_col = c
                break
    if excel_total_col is None:
        excel_total_col = "Subtotal" if "Subtotal" in df_clean.columns else None

    # sumar totales (saltando None)
    def safe_sum(series):
        return float(sum([v for v in series if v is not None]))

    total_monto_pdf = safe_sum(df_clean.get("total", []))
    total_monto_excel = safe_sum(df_clean.get(excel_total_col, [])) if excel_total_col else 0.0
    diferencia_global = safe_sum(df_clean.get("diferencia_monto", []))

    # métricas por estado
    estado_series = [r.get("estado") for r in df_clean.to_dict(orient="records")]
    total_match = sum(1 for s in estado_series if s == "Coincide")
    total_diferencias = sum(1 for s in estado_series if s == "Diferencia detectada")
    total_solo_pdf = sum(1 for s in estado_series if s == "Factura solo en PDF")
    total_solo_excel = sum(1 for s in estado_series if s == "Factura solo en Excel")
    porcentaje_coincidencia = round((total_match / total_pdf) * 100, 2) if total_pdf and total_pdf > 0 else 0.0

    # top 5 discrepancias absolutas
    df_tmp = pd.DataFrame(df_clean)
    if "diferencia_monto" in df_tmp.columns:
        df_tmp["abs_diff"] = df_tmp["diferencia_monto"].apply(lambda x: abs(x) if x is not None else 0)
        top_5 = df_tmp.sort_values("abs_diff", ascending=False).head(5).drop(columns=["abs_diff"]).to_dict(orient="records")
    else:
        top_5 = []

    result = {
        "metadata": {
            "herramientas": ["pdfplumber", "regex", "pandas"],
            "total_facturas_pdf": int(total_pdf),
            "total_facturas_excel": int(total_excel),
            "fecha_ejecucion": datetime.now().isoformat()
        },
        "resumen_conciliacion": {
            "total_monto_pdf": float(total_monto_pdf),
            "total_monto_excel": float(total_monto_excel),
            "diferencia_global": float(diferencia_global),
            "total_coincidencias": int(total_match),
            "total_con_diferencias": int(total_diferencias),
            "solo_en_pdf": int(total_solo_pdf),
            "solo_en_excel": int(total_solo_excel),
            "porcentaje_coincidencia": float(porcentaje_coincidencia),
            "top_5_discrepancias": top_5
        },
        "detalle_conciliacion": df_clean.to_dict(orient="records"),
        "errores_y_excepciones": errores
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False, default=str)
