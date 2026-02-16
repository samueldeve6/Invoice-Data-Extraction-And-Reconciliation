import re
import pandas as pd
import numbers

"""
    Normaliza NIT eliminando:
    - Prefijo CO
    - Guiones
    - Puntos
    - Espacios
    - Cualquier carácter no numérico
"""

def normalize_nit(nit):
    if nit is None:
        return None
    s = str(nit).upper()
    s = s.replace("CO", "")
    s = re.sub(r"[^\d]", "", s)   # deja solo dígitos
    return s if s and s != "0" else None


def clean_money(value):
    """
    Convierte montos en cualquier formato (Excel/PDF/contable)
    a float seguro.

    Soporta:
    - $ 1.234.567,89
    - 1,234,567.89
    - (1.234.567,89)
    - -1.234.567,89
    - valores numéricos directos
    """
    # Si ya es número, devolver como float
    if isinstance(value, numbers.Number):
        return float(value)

    if pd.isna(value) or value is None:
        return 0.0

    value = str(value).strip()

    if value == "":
        return 0.0

    # Detectar negativo con paréntesis
    negative = False
    if value.startswith("(") and value.endswith(")"):
        negative = True
        value = value[1:-1]

    value = value.replace("$", "").replace("COP", "").strip()

    # Caso donde hay punto y coma (formato colombiano)
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    else:
        # Solo puntos
        if value.count(".") == 1:
            parts = value.split(".")
            if len(parts[1]) != 2:
                value = value.replace(".", "")
        else:
            value = value.replace(".", "").replace(",", ".")

    value = re.sub(r"[^\d\.]", "", value)

    try:
        number = float(value) if value != "" else 0.0
        return -number if negative else number
    except:
        return 0.0


def format_date(date_value):
    """
    Convierte fechas a formato ISO YYYY-MM-DD.
    Soporta:
    - string
    - datetime
    - fechas Excel
    """
    if pd.isna(date_value) or date_value is None:
        return None

    try:
        return pd.to_datetime(date_value, dayfirst=True).strftime("%Y-%m-%d")
    except:
        return None
