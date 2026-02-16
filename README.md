📄 PRUEBA TÉCNICA – JUNIOR DATA ENGINEER (IA & AUTOMATIZACIÓN)
1. Objetivo

Diseñar e implementar un sistema en Python que:

Extraiga información estructurada desde facturas en PDF (carpeta Invoices/).

Limpie y transforme el archivo Excel AP Listing.

Realice un cruce y conciliación entre ambas fuentes usando el NIT normalizado como llave principal.

Genere un archivo JSON con el resultado de la conciliación, incluyendo coincidencias, diferencias y métricas globales.

2. Metodología Implementada
2.1 Exploración y Comprensión de Datos
📊 Análisis del Excel (AP Listing)

~55 registros y 48 columnas.

Hojas auxiliares: Summary y Category.

Campos clave:

Supplier/Beneficiary Name

NIT

Subtotal

Invoice ID

VAT/WHT1

Invoice Date

🧾 Análisis de PDFs

Se identificaron distintos tipos de factura:

Electrónica estándar

Servicios públicos

POS / equivalentes

Se documentaron:

Ubicación variable de campos financieros.

Diferentes formatos de fecha (DD/MM/YYYY, YYYY-MM-DD).

Formatos numéricos colombianos:

Puntos = miles

Comas = decimales

🔑 Campo Puente

El NIT fue identificado como llave principal de cruce.

Desafíos:

Prefijos como "CO"

Guiones y puntos

Dígito de verificación

Diferentes longitudes

Se implementó normalización eliminando:

Caracteres no numéricos

Prefijos

Dígito de verificación (cuando aplica)

3. Arquitectura de la Solución
🔹 1. Extracción de PDFs

Se utilizó:

pdfplumber para lectura estructurada

regex robustos para detección de campos

Funciones de normalización personalizadas

Validaciones financieras

Campos extraídos:

Cabecera

nombre_proveedor

nit_proveedor

digito_verificacion

numero_factura

fecha_inicio (emisión)

fecha_final (vencimiento)

moneda

Financieros

subtotal

iva_porcentaje

iva_monto

otros_impuestos

total

numero_lineas

Referencia

orden_compra (formato validado: PO-YCOXX-XXXXXX)

cufe

tipo_factura (electrónica / equivalente / pos)

Validaciones implementadas

subtotal + IVA + otros ≈ total

Inferencia automática del porcentaje IVA si no está explícito

Manejo de PDFs escaneados (sin texto)

🔹 2. Limpieza y Transformación del Excel

Se realizó:

Carga con pandas

Normalización de NIT

Conversión de montos a tipo numérico

Estandarización de nombres (upper + strip)

Conversión de fechas a formato YYYY-MM-DD

Se creó un dataset maestro con:

proveedores solo_pdf

proveedores solo_excel

proveedores en ambas fuentes

4. Cruce y Conciliación
4.1 Estrategia de JOIN

JOIN principal por:

nit_normalized


Clasificación por proveedor:

match

solo_pdf

solo_excel

4.2 Comparaciones realizadas

Para proveedores en ambas fuentes:

Comparación de nombres

Comparación de subtotal

Comparación de IVA

Comparación de total

Coincidencia de número de factura

Diferencia absoluta y porcentual

Se generaron alertas clasificadas como:

✅ Coinciden

Factura presente en ambas fuentes y montos consistentes.

⚠️ Difieren

Se identifican discrepancias en:

Montos

Fechas

Nombre proveedor

Número de factura

4.3 Métricas Globales

El JSON final incluye:

Total proveedores PDF

Total proveedores Excel

Total matches

Total diferencias

Top discrepancias

Resumen ejecutivo con hallazgos