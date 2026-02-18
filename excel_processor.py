import pandas as pd
import re
import numbers

def normalize_po(value):
    if pd.isna(value) or value is None:
        return None
    s = str(value).strip()
    garbage_terms = ['NENTES', 'NSABLES', 'SABLES', 'ENTES', 'PONSABLES', 'NENTES']
    if s.upper() in garbage_terms:
        return None
    if len(s) < 5 or not any(char.isdigit() for char in s):
        if not s.upper().startswith("PO"):
            return None
    return s

def normalize_nit(nit):
    if pd.isna(nit):
        return None
    nit = str(nit).upper().replace("CO", "")
    nit = re.sub(r"[^\d]", "", nit)
    return nit if nit else None

def parse_number(value):
    if isinstance(value, numbers.Number):
        try:
            return float(value)
        except:
            return 0.0
    if pd.isna(value):
        return 0.0
    s = str(value).strip()
    if s == "":
        return 0.0
    s = s.replace("$", "").replace("COP", "").replace("USD", "").strip()
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        if "." in s and "," not in s:
            parts = s.split(".")
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
                s = s.replace(".", "")
        s = s.replace(",", ".")
    
    s = re.sub(r"[^\d\.]", "", s)
    try:
        num = float(s) if s != "" else 0.0
        return -num if neg else num
    except:
        return 0.0

def normalize_text(value):
    if pd.isna(value):
        return None
    return str(value).strip().upper()

def normalize_invoice_id(value):
    if pd.isna(value):
        return None
    s = str(value).strip().upper()
    if re.fullmatch(r"\d+\.0", s):
        s = s.split(".", 1)[0]
    s = re.sub(r"\s+", "", s)
    return s

def normalize_date(value):
    if pd.isna(value):
        return None
    try:
        return pd.to_datetime(value, dayfirst=True).strftime("%Y-%m-%d")
    except:
        return None
def load_excel(path):
    # 1. Carga cruda del archivo
    df_raw = pd.read_excel(path, header=None)
    
    # 2. Encontrar la fila de encabezados
    header_row = None
    for i, row in df_raw.iterrows():
        if row.astype(str).str.contains("NIT", case=False, na=False).any():
            header_row = i
            break
    
    if header_row is None:
        raise Exception("No se encontró la fila con 'NIT'")

    # 3. Cargar con encabezados correctos
    df = pd.read_excel(path, header=header_row)
    df.columns = df.columns.astype(str).str.strip()
    
    # --- PROCESO DE EXTRACCIÓN MANUAL (SOLUCIÓN DEFINITIVA) ---
    # --- LIMPIEZA SEGURA DE COLUMNAS NUMÉRICAS IMPORTANTES ---

    df.columns = df.columns.str.strip()

    col_subtotal = next((c for c in df.columns if c.upper() == "SUBTOTAL"), None)
    col_amount_total = next((c for c in df.columns if "AMOUNT TOTAL" in c.upper()), None)
    col_total_pagar = next((c for c in df.columns if "TOTAL A PAGAR" in c.upper()), None)
    col_vat = next((c for c in df.columns if "VAT" in c.upper() and "TOTAL" not in c.upper()), None)

    if col_subtotal:
        df["subtotal_excel"] = df[col_subtotal].apply(parse_number)
    else:
        df["subtotal_excel"] = 0.0

    if col_amount_total:
        df["amount_total_excel"] = df[col_amount_total].apply(parse_number)
    elif col_total_pagar:
        df["amount_total_excel"] = df[col_total_pagar].apply(parse_number)
    else:
        df["amount_total_excel"] = 0.0

    if col_vat:
        df["vat_excel"] = df[col_vat].apply(parse_number)
    else:
        df["vat_excel"] = 0.0

    

    # 4. Aplicar normalizaciones básicas
    nit_cols = [c for c in df.columns if "NIT" in c.upper()]
    df["nit_normalized"] = df[nit_cols[0]].apply(normalize_nit) if nit_cols else None

    inv_cols = [c for c in df.columns if "INVOICE ID" in c.upper()]
    df["invoice_id_normalized"] = df[inv_cols[0]].apply(normalize_invoice_id) if inv_cols else None

    # 5. ASIGNACIÓN CRÍTICA DEL TOTAL
    # Intentamos buscar la columna "Total a Pagar" directamente primero
    col_pagar = next((c for c in df.columns if "TOTAL A PAGAR" in c.upper()), None)
    
    if col_pagar:
        df['total_excel'] = df[col_pagar].apply(parse_number)

    # 6. Limpieza final
    df = df.dropna(subset=['nit_normalized', 'invoice_id_normalized'])
    df = df.reset_index(drop=True)

    if not df.empty:
        print(f"DEBUG FINAL - Valor en Excel: {df['total_excel'].iloc[0]}")

    return df