"""
pdf_extractor.py
Extracción robusta de campos desde PDFs con pdfplumber + regex.
Mejoras:
- Más patrones para NIT, factura, fechas (ES/EN).
- Normalización de NIT incluida aquí para facilitar el cruce.
- Mejor parseo de montos (soporta formatos colombianos).
- Devuelve None si PDF es escaneado o inválido (para que main lo registre).
"""

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
    # quitar dígito de verificación si tiene más de 9 dígitos
    if len(s) > 9:
        s = s[:9]
    return s if s and s != "0" else None

def normalize_date(date_str):
    """Función que faltaba en tu código"""
    if not date_str:
        return None
    try:
        # Limpiar y estandarizar separadores
        d = date_str.strip().replace("/", "-")
        # Si es DD-MM-YYYY -> YYYY-MM-DD
        if re.match(r'^\d{2}-\d{2}-\d{4}$', d):
            parts = d.split("-")
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        # Si ya es YYYY-MM-DD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', d):
            return d
        return d
    except:
        return date_str


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
            # Si hay grupos de captura, usar el primero
            if m.groups():
                return m.group(1).strip()
            # Si no hay grupos, devolver todo el match
            else:
                return m.group(0).strip()
    return None


def extract_best_amount(patterns, text):
    """Busca *todos* los montos que coincidan con los patrones y retorna el más probable.

    En muchos PDFs aparecen múltiples 'Total' (ej. totales parciales, totales de líneas).
    Para el campo total a pagar, normalmente el valor correcto es el monto más alto.
    """
    candidates = []
    for p in patterns:
        try:
            matches = re.findall(p, text, flags=re.IGNORECASE)
        except re.error:
            matches = []

        for m in matches:
            raw = m if isinstance(m, str) else (m[0] if m else None)
            if not raw:
                continue
            val = parse_number(raw)
            if val and val > 0:
                candidates.append((val, raw))

    if not candidates:
        return None

    # Elegir el monto mayor como heurística principal
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]



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

def extract_digito_verificacion(nit_completo):
    """
    Extrae el dígito de verificación de un NIT completo.
    Si el NIT tiene 10+ dígitos, el último es el DV.
    Si tiene 9 dígitos, no tiene DV claro.
    """
    if not nit_completo:
        return None
    
    nit_str = str(nit_completo)
    if len(nit_str) >= 10:
        return nit_str[-1]  # último dígito
    elif len(nit_str) == 9:
        return None  # no se puede determinar el DV
    else:
        return None






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

    # --- LÓGICA DE FECHAS MEJORADA (Prioridad 2026) ---
    def get_best_date(patterns, text_source, date_type=""):
        print(f"DEBUG - BUSCANDO {date_type} con {len(patterns)} patrones...")
        found_dates = []
        
        try:
            for i, p in enumerate(patterns):
                # Usamos findall para capturar todas las fechas que coincidan con el patrón
                matches = re.findall(p, text_source, re.IGNORECASE)
                if matches:
                    print(f"DEBUG - Patrón {i+1} ({p[:50]}...) encontró {len(matches)} coincidencias")
                    for m in matches:
                        # Si el patrón tiene grupos, re.findall devuelve tuplas o strings
                        d_str = m if isinstance(m, str) else m[0]
                        if d_str:
                            found_dates.append(d_str.strip())
                            print(f"DEBUG -     → Fecha encontrada: {d_str.strip()}")
                else:
                    if i < 5:  # Solo mostrar primeros 5 para no saturar
                        print(f"DEBUG - Patrón {i+1} ({p[:50]}...) - SIN coincidencias")
            
            print(f"DEBUG - {date_type} - Fechas encontradas: {found_dates}")
            
            if not found_dates:
                print(f"DEBUG - {date_type} - NO SE ENCONTRARON FECHAS")
                return None
                
            # Prioridad absoluta: Buscar fechas que contengan "2026"
            dates_2026 = [d for d in found_dates if "2026" in d]
            
            if dates_2026:
                result = normalize_date(dates_2026[0])
                print(f"DEBUG - {date_type} - Seleccionada fecha 2026: {result}")
                return result
            
            result = normalize_date(found_dates[0])
            print(f"DEBUG - {date_type} - Seleccionada primera fecha: {result}")
            return result
            
        except Exception as e:
            print(f"ERROR - {date_type} - Error en get_best_date: {e}")
            return None

    # NOMBRE PROVEEDOR
    nombre_proveedor = extract_value([
        r"Proveedor\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ\s&\.]{3,50}?)(?:\s{2,}|NIT|C\.?N\.?U\.?I\.?T\.?|$)",
        r"Raz[oó]n Social\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ\s&\.]{3,50}?)(?:\s{2,}|NIT|C\.?N\.?U\.?I\.?T\.?|$)",
        r"Supplier\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ\s&\.]{3,50}?)(?:\s{2,}|NIT|Tax\s*ID|$)",
        r"Supplier/Beneficiary Name\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ\s&\.]{3,50}?)(?:\s{2,}|NIT|Invoice|$)",
        r"Nombre\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ\s&\.]{3,50}?)(?:\s{2,}|NIT|$)",
        r"Denominaci[oó]n\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ\s&\.]{3,50}?)(?:\s{2,}|NIT|$)",
        r"^([A-ZÁÉÍÓÚÑ\s&\.S\.A\.S\.\,]{5,60}?)\s+(?:NIT|C\.?N\.?U\.?I\.?T\.?|Tax\s*ID)\s*[:\-]?\s*\d"
    ], text)
    
    if not nombre_proveedor or len(nombre_proveedor.strip()) > 100:
        filename = os.path.basename(pdf_path)
        parts = filename.replace(".pdf", "").split("_")
        if len(parts) >= 3:
            nombre_proveedor = " ".join(parts[1:-1]).strip()
        elif len(parts) == 2:
            nombre_proveedor = parts[0].replace("YCO01", "").strip()
    
    if nombre_proveedor and len(nombre_proveedor) > 80:
        nombre_proveedor = nombre_proveedor[:80].strip()

    # NIT
    nit_candidates = extract_nit(text)
    nit = max(nit_candidates, key=len) if nit_candidates else None
    digito_verificacion = extract_digito_verificacion(nit) if nit else None

    # NUMERO FACTURA
    numero_factura = os.path.basename(pdf_path).split("_")[-1].replace(".pdf", "").strip()

    # --- EXTRACCIÓN DE FECHAS CON NUEVOS NOMBRES Y PATRONES ---
    print(f"DEBUG - Iniciando extracción de fechas para {os.path.basename(pdf_path)}")
    
    p_inicio_patrones = [
        r"Fecha\s+Expedici[oó]n\s*:\s*(\d{4}-\d{2}-\d{2})",
        r"Fecha\s+Expedici[oó]n\s*:\s*(\d{2}/\d{2}/\d{4})",
        r"Fecha\s+Expedici[oó]n\s*:\s*(\d{2}-\d{2}-\d{4})",
        # Patrones Request Date
        r"Request\s+Date\s*\(\*?\)\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Request\s+Date\s*\(\*?\)\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Request\s+Date\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Request\s+Date\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        # Patrones FECHA INICIO
        r"FECHA\s*INICIO\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"FECHA\s*INICIO\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Fecha\s*Inicio\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Fecha\s*Inicio\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        # Patrones Invoice Date
        r"Invoice\s+Date\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Invoice\s+Date\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        # Patrones genéricos
        r"Fecha\s*(?:Emisi[oó]n)?\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Fecha\s*(?:Emisi[oó]n)?\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Date\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"(\d{4}[\/\-]\d{2}[\/\-]\d{2})"
    ]
    
    p_final_patrones = [
        # Patrones Fecha Vencimiento
        r"Fecha\s+Vencimiento\s*:\s*(\d{4}-\d{2}-\d{2})",
        r"Fecha\s+Vencimiento\s*:\s*(\d{2}/\d{2}/\d{4})",
        r"Fecha\s+Vencimiento\s*:\s*(\d{2}-\d{2}-\d{4})",
        # Patrones FECHA FINAL
        r"FECHA\s*FINAL\s*:\s*(\d{4}-\d{2}-\d{2})",
        r"FECHA\s*FINAL\s*:\s*(\d{2}/\d{2}/\d{4})",
        r"FECHA\s*FINAL\s*:\s*(\d{2}-\d{2}-\d{4})",
        # Patrones Due Date
        r"Due\s+Date\s*\(\*?\)\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Due\s+Date\s*\(\*?\)\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Due\s+Date\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Due\s+Date\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        # Patrones Vencimiento
        r"Fecha\s*Vencimiento\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Fecha\s*Vencimiento\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Vencimiento\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Vencimiento\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        # Patrones genéricos
        r"Vence[:\s]*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Vence[:\s]*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        # Búsqueda genérica de fechas (como fallback) - MÁS AMPLIO
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        # Patrones adicionales para facturas colombianas
        r"Fecha\s*de\s*vencimiento\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Fecha\s*de\s*vencimiento\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})",
        r"Vence\s*el\s*[:\-]?\s*(\d{2}[\/\-]\d{2}[\/\-]\d{4})",
        r"Vence\s*el\s*[:\-]?\s*(\d{4}[\/\-]\d{2}[\/\-]\d{2})"
    ]

    print(f"DEBUG - Total patrones inicio: {len(p_inicio_patrones)}, final: {len(p_final_patrones)}")
    
    fecha_inicio = get_best_date(p_inicio_patrones, text, "fecha_inicio")
    fecha_final = get_best_date(p_final_patrones, text, "fecha_final")
    
    print(f"DEBUG FINAL - fechas extraídas: inicio={fecha_inicio}, final={fecha_final}")

    # MONTOS (Mantenemos todos)
    subtotal_raw = extract_value([r"Subtotal\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)"], text)
    iva_raw = extract_value([r"IVA\s*(?:[:\-]|\s)\s*([\d\.,\(\)]+)", r"VAT\s*(?:[:\-]|\s)\s*([\d\.,\(\)]+)"], text)

    total_patterns = [
        r"Total\s+a\s+Pagar\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
        r"Total\s*(?:a\s*Pagar|Factura|General|con\s*IVA)?\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
        r"Valor\s*Total\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
        r"Amount\s*Total\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
        r"Total\s*COP\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)"
    ]

    # Usar heurística "mejor monto" para evitar capturar totales parciales pequeños
    total_raw = extract_best_amount(total_patterns, text) or extract_value(total_patterns, text)

    subtotal = parse_number(subtotal_raw)
    iva_monto = parse_number(iva_raw)
    total = parse_number(total_raw)

    # IVA PORCENTAJE (Asegurado como entero)
    iva_porcentaje = None
    iva_pct_raw = extract_value([r"IVA\s*[:\-]?\s*(\d+)%?", r"(\d{1,2})\s*%?\s*IVA"], text)
    if iva_pct_raw and iva_pct_raw.isdigit():
        iva_porcentaje = int(iva_pct_raw)

    # OTROS IMPUESTOS
    otros_impuestos = 0.0
    otros_raw = extract_value([r"Otros impuestos\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)",
                               r"Retenci[oó]n\s*[:\-]?\s*\$?\s*([\d\.,\(\)]+)"], text)
    if otros_raw:
        otros_impuestos = parse_number(otros_raw)

    # PO / CUFE / MONEDA / LINEAS
    orden_compra = extract_value([r"PO\#?\s*[:\-]?\s*([A-Z0-9\-\_/]+)", r"PO\s*[:\-]?\s*(PO-[A-Z0-9\-\_]+)"], text)
    cufe = extract_value([r"CUFE\s*[:\-]?\s*([a-f0-9]{10,})", r"CUFE\s*[:\-]?\s*([A-Z0-9]{10,})"], text)
    tipo_factura = "electrónica" if re.search(r"factura electrónica|electr[oó]nica", text, re.IGNORECASE) else None
    
    moneda = extract_value([
        r"Moneda\s*[:\-]?\s*([A-Z]{3})",
        r"Currency\s*[:\-]?\s*([A-Z]{3})",
        r"\b(COP|USD|EUR)\b"
    ], text)
    moneda = moneda.upper().strip() if moneda else "COP"

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
    
    if total == 0.0 and not numero_factura and not nit:
        return None

    # --- DICCIONARIO FINAL CON CAMPOS RENOMBRADOS ---
    return {
        "source_file": os.path.basename(pdf_path),
        "nombre_proveedor": nombre_proveedor,
        "nit_proveedor": nit[:-1] if nit and len(nit) > 9 else nit,
        "nit_normalized": nit_normalized,
        "digito_verificacion": digito_verificacion,
        "numero_factura": numero_factura,
        "invoice_id_normalized": normalize_invoice_id(numero_factura),
        "fecha_inicio": fecha_inicio,        # Renombrado
        "fecha_final": fecha_final,          # Renombrado
        "moneda": moneda,
        "subtotal": subtotal,
        "iva_porcentaje": iva_porcentaje,    # Entero
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
