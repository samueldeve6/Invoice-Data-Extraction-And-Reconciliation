"""
reconciler.py
Hace reconciliación en dos pasos:
- Merge exacto por (nit_normalized, invoice id)
- Merge por nit_normalized (fallback) para detectar coincidencias por NIT aunque invoice difiera
Calcula diferencias y clasifica filas.
"""
import pandas as pd
import numpy as np

def reconcile(pdf_df, excel_df):
    pdf = pdf_df.copy()
    excel = excel_df.copy()

    # asegurar columnas existan
    if "nit_normalized" not in pdf.columns:
        pdf["nit_normalized"] = pdf.get("nit_proveedor").fillna("").astype(str).str.replace(r"[^\d]", "", regex=True)
    if "nit_normalized" not in excel.columns:
        excel["nit_normalized"] = excel.get("NIT").astype(str).apply(lambda x: "" if pd.isna(x) else str(x).upper().replace("CO","").replace(" ",""))

    # identificar invoice column en excel (Invoice ID preferido)
    invoice_col = None
    for c in excel.columns:
        if "INVOICE ID" in str(c).upper() or str(c).upper() == "INVOICE":
            invoice_col = c
            break
    if invoice_col is None:
        # fallback: tomar primera columna que contenga 'INVOICE' o 'INVOICE ID'
        for c in excel.columns:
            if "INVOICE" in str(c).upper():
                invoice_col = c
                break

    # normalizaciones simples
    if "numero_factura" in pdf.columns:
        pdf["numero_factura"] = pdf["numero_factura"].fillna("").astype(str).str.strip()
    else:
        pdf["numero_factura"] = ""

    if invoice_col:
        excel[invoice_col] = excel[invoice_col].fillna("").astype(str).str.strip()
    else:
        excel["Invoice ID"] = excel.get("Invoice ID", "").astype(str).fillna("")

    excel_col_for_merge = invoice_col if invoice_col else "Invoice ID"

    pdf["invoice_id_normalized"] = (
        pdf["invoice_id_normalized"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    excel["invoice_id_normalized"] = (
        excel["invoice_id_normalized"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    
    def clean_nit(nit):
        nit = str(nit)
        nit = "".join(c for c in nit if c.isdigit())
        if len(nit) > 9:
            nit = nit[:9]  # quitar dígito verificación
        return nit

    pdf["nit_normalized"] = pdf["nit_normalized"].apply(clean_nit)
    excel["nit_normalized"] = excel["nit_normalized"].apply(clean_nit)

    print("PDF invoice_id_normalized dtype:", pdf["invoice_id_normalized"].dtype)
    print("Excel invoice_id_normalized dtype:", excel["invoice_id_normalized"].dtype)

    print("PDF NIT únicos:")
    print(pdf["nit_normalized"].unique()[:10])

    print("Excel NIT únicos:")
    print(excel["nit_normalized"].unique()[:10])

    # ---- 1) merge exacto por nit + invoice normalizado ----
    merged = pd.merge(
        pdf,
        excel,
        on="invoice_id_normalized",
        how="outer",
        indicator=True,
        suffixes=("_pdf", "_excel")
    )

    merged["nit_coincide"] = (
        merged["nit_normalized_pdf"] == merged["nit_normalized_excel"]
    )

    merged["nit_coincide"] = merged["nit_coincide"].fillna(False)


    print("PDF invoices únicos:")
    print(pdf["invoice_id_normalized"].unique()[:10])

    print("Excel invoices únicos:")
    print(excel["invoice_id_normalized"].unique()[:10])



    # clasificacion básica
    merged["clasificacion"] = merged["_merge"].map({
        "both": "match",
        "left_only": "solo_pdf",
        "right_only": "solo_excel"
    }).astype("object")  

    # detectar columna monto en excel
    excel_total_col = None
    for c in merged.columns:
        if "TOTAL A PAGAR" in str(c).upper():
            excel_total_col = c
            break
    if excel_total_col is None:
        for c in merged.columns:
            if "AMOUNT TOTAL" in str(c).upper() or "AMOUNT" in str(c).upper():
                excel_total_col = c
                break
    if excel_total_col is None:
        # fallback: SUBTOTAL
        excel_total_col = "Subtotal" if "Subtotal" in merged.columns else None

    # asegurar columnas total en df
    merged["total"] = merged.get("total", 0).fillna(0)
    if excel_total_col and excel_total_col in merged.columns:
        merged[excel_total_col] = merged[excel_total_col].fillna(0)
    else:
        # crear columna si no existe
        merged["__excel_total__"] = 0
        excel_total_col = "__excel_total__"

    # diferencias
    merged["diferencia_monto"] = merged["total"] - merged[excel_total_col]
    def safe_pct(row):
        ex = row[excel_total_col]
        if ex == 0 or ex is None:
            return None
        return (row["diferencia_monto"] / ex) * 100
    merged["diferencia_porcentual"] = merged.apply(safe_pct, axis=1)

    # estado final
    def estado(row):
        if row["clasificacion"] == "solo_pdf":
            return "Factura solo en PDF"
        if row["clasificacion"] == "solo_excel":
            return "Factura solo en Excel"
        # match: comparar valores aproximados
        if abs(row["diferencia_monto"]) < 1:
            return "Coincide"
        return "Diferencia detectada"
    merged["estado"] = merged.apply(estado, axis=1)

    # ----- 2) fallback: buscar posibles coincidencias solo por NIT cuando no hubo match ----
    # construir lista de pdfs y excels sin match y tratar de encontrar coincidencias por NIT
    left_only = merged[merged["_merge"] == "left_only"]
    right_only = merged[merged["_merge"] == "right_only"]

    if not left_only.empty and not right_only.empty:
        # for performance: crear diccionario por nit en excel
        excel_by_nit = {}
        for _, r in right_only.iterrows():
            nit = r.get("nit_normalized")
            if pd.isna(nit) or nit in (None, ""):
                continue
            excel_by_nit.setdefault(str(nit), []).append(r.to_dict())

        # intentar emparejar left_only por nit
        updates = []
        for idx, r in left_only.iterrows():
            nit = r.get("nit_normalized")
            if pd.isna(nit) or nit in (None, ""):
                continue
            candidates = excel_by_nit.get(str(nit))
            if candidates:
                # emparejar con el primer candidato (podríamos mejorar con heurística)
                cand = candidates[0]
                # mark row: create merged composite by concatenation - simpler devolver marca en columna 'possible_match'
                merged.at[idx, "possible_match_invoice"] = cand.get(excel_col_for_merge)
                merged.at[idx, "possible_match_tot_excel"] = cand.get(excel_total_col)
                merged.at[idx, "clasificacion"] = "possible_match_by_nit"

    return merged