"""
pdf_extractor.py
Extracción robusta de campos desde PDFs con pdfplumber + regex.
Mejoras:
- Más patrones para NIT, factura, fechas (ES/EN).
- Normalización de NIT incluida aquí para facilitar el cruce.
- Mejor parseo de montos (soporta formatos colombianos).
- Devuelve None si PDF es escaneado o inválido (para que main lo registre).
"""
from email.mime import text
import pdfplumber
import re
import os

# ---------- utilidades internas ----------
def normalize_invoice_id(value):
    if not value:
        return None
    return str(value).strip().upper().replace(" ", "")

def clean_text(text):
    if not text:
        return ""
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def normalize_nit(nit):
    if nit is None:
        return None
    s = str(nit).upper()
    s = s.replace("CO", "")
    s = re.sub(r"[^\d]", "", s)   # deja solo dígitos
    return s if s and s != "0" else None


def parse_number(value):
    if value is None:
        return 0.0
    s = str(value).strip()
    if s == "":
        return 0.0
    # limpiar símbolos
    s = s.replace("$", "").replace("COP", "").strip()
    # negativos en paréntesis
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    # decidir formato
    # si tiene both ',' and '.' decide según posición
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # estilo 1.234.567,89
        else:
            s = s.replace(",", "")  # estilo 1,234,567.89
    else:
        s = s.replace(".", "").replace(",", ".")
    s = re.sub(r"[^\d\.]", "", s)
    try:
        num = float(s) if s != "" else 0.0
        return -num if neg else num
    except:
        return 0.0

def extract_value(patterns, text, first_only=True):
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None



def extract_nit(text):
    if not text:
        return []

    cleaned = []

    # 1️⃣ NIT explícitos con palabras clave
    matches = re.findall(
        r"(?:C\/?NIT|NIT|Tax\s*ID)[^\d]{0,20}([\d\.,\-\s]{8,25})",
        text,
        re.IGNORECASE
    )

    # 2️⃣ Números sueltos de 8 a 10 dígitos (posibles NITs)
    loose_matches = re.findall(
        r"\b\d{8,10}\b",
        text
    )

    all_matches = matches + loose_matches

    for m in all_matches:
        m = m.strip()

        # limpiar puntos, comas y espacios
        m = re.sub(r"[^\d\-]", "", m)

        # manejar guion
        if "-" in m:
            left, right = m.split("-", 1)
            left = left.strip()
            right = right.strip()
            # conservar DV si es dígito
            if right.isdigit() and len(right) == 1:
                m = left + right
            else:
                m = left  # guion vacío o no dígito → eliminar

        # dejar solo números
        digits = re.sub(r"[^\d]", "", m)

        # aceptar solo NITs entre 8 y 11 dígitos (para incluir DV)
        if 8 <= len(digits) <= 11:
            cleaned.append(digits)

    # eliminar duplicados y vacíos
    cleaned = list(filter(None, cleaned))
    cleaned = list(dict.fromkeys(cleaned))  # mantener orden y únicos

    return cleaned






# ---------- extracción ----------
def extract_invoice_data(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + " "
    except Exception as e:
        print(f"⚠ Error abriendo PDF {pdf_path}: {e}")
        return None

    text = clean_text(text)
    print(f"DEBUG {os.path.basename(pdf_path)} - caracteres detectados: {len(text)}")
    if len(text) < 20:
        print(f"⚠ PDF SIN TEXTO DETECTADO (posible escaneado): {pdf_path}")
        return None

    # NOMBRE PROVEEDOR (varios patrones)
    nombre_proveedor = extract_value([
        r"Proveedor\s*[:\-]\s*(.+?)(?:\s{2,}|,|$)",
        r"Raz[oó]n Social\s*[:\-]\s*(.+?)(?:\s{2,}|,|$)",
        r"Supplier\s*[:\-]\s*(.+?)(?:\s{2,}|,|$)",
        r"Supplier/Beneficiary Name\s*[:\-]\s*(.+?)(?:\s{2,}|,|$)"
    ], text)

    # NIT
    nit = extract_nit(text)


    # NUMERO FACTURA desde nombre del archivo
    filename = os.path.basename(pdf_path)
    numero_factura = filename.split("_")[-1].replace(".pdf", "").strip()

    # FECHA EMISION (dd/mm/yyyy or yyyy-mm-dd)
    fecha_emision = extract_value([
        r"Fecha\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Invoice Date\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Fecha Emisi[oó]n\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})"
    ], text)

    # SUBTOTAL / IVA / TOTAL (varios patrones)
    subtotal_raw = extract_value([r"Subtotal\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)"], text)
    iva_raw = extract_value([r"IVA\s*(?:[:\-]|\s)\s*([\d\.,\(\)]+)", r"VAT\s*(?:[:\-]|\s)\s*([\d\.,\(\)]+)"], text)
    total_raw = extract_value([
    r"Total\s*(?:a\s*Pagar|Factura|General|con\s*IVA)?\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
    r"Valor\s*Total\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
    r"Amount\s*Total\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
    r"Total\s*COP\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)"
    ], text)


    subtotal = parse_number(subtotal_raw)
    iva_monto = parse_number(iva_raw)
    total = parse_number(total_raw)

    # IVA porcentaje si aparece (ej: IVA 19%)
    iva_porcentaje = None
    iva_pct_raw = extract_value([
    r"IVA\s*[:\-]?\s*(\d+)%?",
    r"(\d{1,2})\s*%?\s*IVA"
    ], text)

    if iva_pct_raw and iva_pct_raw.isdigit():
        iva_porcentaje = int(iva_pct_raw)

    # otros_impuestos (intentar detectar ICO o retenciones)
    otros_impuestos = 0.0
    otros_raw = extract_value([r"Otros impuestos\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
                               r"Retenci[oó]n\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)"], text)
    if otros_raw:
        otros_impuestos = parse_number(otros_raw)

    # PO / CUFE / tipo de factura
    orden_compra = extract_value([r"PO\#?\s*[:\-]?\s*([A-Z0-9\-\_/]+)", r"PO\s*[:\-]?\s*(PO-[A-Z0-9\-\_]+)"], text)
    cufe = extract_value([r"CUFE\s*[:\-]?\s*([a-f0-9]{10,})", r"CUFE\s*[:\-]?\s*([A-Z0-9]{10,})"], text)
    tipo_factura = "electrónica" if re.search(r"factura electrónica|electr[oó]nica", text, re.IGNORECASE) else None

    # numero_lineas: intentar contar líneas de tabla en la primera página si es posible
    numero_lineas = None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                table = pdf.pages[0].extract_table()
                if table:
                    numero_lineas = max(0, len(table)-1)
    except:
        numero_lineas = None

    nit_normalized = normalize_nit(nit)

    # validación mínima: número de factura o total
    if total == 0.0 and not numero_factura and not nit:
        print(f"⚠ Factura inválida detectada: {pdf_path}")
        return None
    print("Factura detectada:", numero_factura)

    return {
        "source_file": os.path.basename(pdf_path),
        "nombre_proveedor": nombre_proveedor,
        "nit_proveedor": nit,
        "nit_normalized": nit_normalized,
        "digito_verificacion": None,
        "numero_factura": numero_factura,
        "invoice_id_normalized": normalize_invoice_id(numero_factura),
        "fecha_emision": fecha_emision,
        "fecha_vencimiento": None,
        "moneda": None,
        "subtotal": subtotal,
        "iva_porcentaje": iva_porcentaje,
        "iva_monto": iva_monto,
        "otros_impuestos": otros_impuestos,
        "total": total,
        "numero_lineas": numero_lineas,
        "orden_compra": orden_compra,
        "cufe": cufe,
        "tipo_factura": tipo_factura
    }

# helper para procesar carpeta (opcional)
def process_pdfs(folder_path):
    invoices = []
    total_files = 0
    valid_invoices = 0
    empty_pdfs = 0
    for file in os.listdir(folder_path):
        if file.lower().endswith(".pdf"):
            total_files += 1
            path = os.path.join(folder_path, file)
            data = extract_invoice_data(path)
            if isinstance(data, dict):
                invoices.append(data)
                valid_invoices += 1
            else:
                empty_pdfs += 1
    print(f"📊 Total PDFs: {total_files}, válidos: {valid_invoices}, inválidos/escaneados: {empty_pdfs}")
    return invoices
