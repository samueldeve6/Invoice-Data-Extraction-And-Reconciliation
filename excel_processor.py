"""
excel_processor.py
Lectura y limpieza robusta del AP Listing Excel.
- Busca dinámicamente la fila de encabezado que contiene 'NIT'
- Normaliza NITs, convierte montos y asegura Invoice ID
- Devuelve DataFrame limpio listo para merge
"""
import pandas as pd
import re
import numbers

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
    
    # Limpiar símbolos de moneda y prefijos
    s = s.replace("$", "").replace("COP", "").replace("USD", "").strip()
    
    # Manejar negativos en paréntesis
    neg = False
    if s.startswith("(") and s.endswith(""):
        neg = True
        s = s[1:-1]
    
    # Manejar formato colombiano: 1.234.567,89 -> 1234567.89
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # Hay más puntos que comas, formato colombiano
            s = s.replace(".", "").replace(",", ".")
        else:
            # Hay más comas que puntos, formato americano
            s = s.replace(",", "")
    else:
        # Si solo tiene uno de los dos, asumir formato colombiano si tiene puntos
        if "." in s and "," not in s:
            # Verificar si es formato colombiano (miles) o decimal
            parts = s.split(".")
            if len(parts) > 2:
                # Múltiples puntos = formato colombiano de miles
                s = s.replace(".", "")
            elif len(parts) == 2 and len(parts[1]) == 3:
                # Tres dígitos después del punto = probablemente miles
                s = s.replace(".", "")
            else:
                # Un solo punto con 1-2 dígitos = decimal
                pass
        s = s.replace(".", "").replace(",", ".")
    
    # Extraer solo números y punto decimal
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
    # leemos sin header para detectar la fila que contiene "NIT"
    df_raw = pd.read_excel(path, header=None)
    header_row = None
    for i, row in df_raw.iterrows():
        # buscar texto 'NIT' en la fila
        if row.astype(str).str.contains("NIT", case=False, na=False).any():
            header_row = i
            break
    if header_row is None:
        raise Exception("No se encontró la fila de encabezados con 'NIT'")

    df = pd.read_excel(path, header=header_row)
    # limpiar nombres columnas
    df.columns = df.columns.astype(str).str.strip()
    df = df.loc[:, df.columns.notna()]
    df = df.dropna(axis=1, how="all")

    print("Columnas detectadas correctamente:")
    print(df.columns.tolist())

    # Limpieza específica para el formato de Excel compartido
    # Eliminar filas completamente vacías
    df = df.dropna(how='all')
    
    # Limpiar espacios en blanco en todas las columnas de texto
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
        # Reemplazar valores como '#N/D' con NaN
        df[col] = df[col].replace(['#N/D', 'nan', 'NaN', ''], None)

    # Detectar y limpiar montos con formato colombiano específico
    amount_columns = ['Subtotal', 'VAT/WHT1', 'VAT/WHT2', 'VAT/WHT3', 'Amount Total', 
                     'Base / Subtotal', 'VAT Total', 'WHT Total', 'Total a Pagar']
    
    for col in amount_columns:
        if col in df.columns:
            print(f"Limpiando columna de monto: {col}")
            # Aplicar parse_number a cada valor
            df[col] = df[col].apply(parse_number)
            # Mostrar algunos valores para verificar
            print(f"Muestra de {col}: {df[col].head(3).tolist()}")

    # Normalizar fechas
    date_columns = ['Request Date', 'Invoice Date', 'Due Date']
    for col in date_columns:
        if col in df.columns:
            print(f"Normalizando fechas en columna: {col}")
            df[col] = df[col].apply(normalize_date)
            print(f"Muestra de {col}: {df[col].head(3).tolist()}")

    # detectar columna NIT
    nit_cols = [c for c in df.columns if "NIT" in c.upper()]
    if not nit_cols:
        raise Exception("No se encontró columna NIT")
    nit_col = nit_cols[0]

    # normalizar nit
    df["nit_normalized"] = df[nit_col].apply(normalize_nit)
    
    # --- Normalizar nombre proveedor ---
    supplier_cols = [c for c in df.columns if "SUPPLIER" in c.upper()]
    if supplier_cols:
        supplier_col = supplier_cols[0]
        df["supplier_normalized"] = df[supplier_col].apply(normalize_text)

    # --- Normalizar Invoice ID ---
    invoice_cols = [c for c in df.columns if "INVOICE ID" in c.upper()]
    if invoice_cols:
        invoice_col = invoice_cols[0]
        df["invoice_id_normalized"] = df[invoice_col].apply(normalize_invoice_id)

    # --- Normalizar fecha ---
    date_cols = [c for c in df.columns if "INVOICE DATE" in c.upper()]
    if date_cols:
        date_col = date_cols[0]
        df["invoice_date_normalized"] = df[date_col].apply(normalize_date)

    # asegurar Invoice ID
    invoice_cols = [c for c in df.columns if "INVOICE ID" in c.upper() or c.upper() == "INVOICE" or "INVOICE ID" in c.upper()]
    invoice_col = invoice_cols[0] if invoice_cols else None
    if invoice_col:
        df[invoice_col] = df[invoice_col].astype(str).str.strip()
    else:
        # si no hay invoice id explícito, intentar varios candidatos
        possible = [c for c in df.columns if "INVOICE" in c.upper() or "INVOICE ID" in c.upper() or "INVOICEID" in c.upper()]
        invoice_col = possible[0] if possible else None

    # convertir montos a numeric: buscamos columnas con SUBTOTAL / TOTAL / AMOUNT
    numeric_candidates = [c for c in df.columns if any(k in c.upper() for k in ["SUBTOTAL", "TOTAL", "AMOUNT", "BASE / SUBTOTAL"])]
    for col in numeric_candidates:
        df[col] = df[col].apply(parse_number)

    # filtrar filas válidas: nit y invoice (si existe)
    df = df.dropna(how="all")
    df = df[df["nit_normalized"].notna()]
    if invoice_col:
        df = df[df[invoice_col].notna()]
    
    # eliminar filas con NIT inválido
    df = df[df["nit_normalized"].notna()]

    # eliminar filas con invoice vacía
    if "invoice_id_normalized" in df.columns:
        df = df[df["invoice_id_normalized"].notna()]

    df = df.reset_index(drop=True)
    print(f"Total facturas Excel limpias: {len(df)}")
    return df
