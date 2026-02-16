"""
main.py
Orquestador principal — no requiere cambios en la estructura de carpetas.
Asegúrate de tener:
- carpeta Invoices/ con los PDFs
- el archivo Excel en la raíz con el nombre usado en load_excel()
"""
import os
import pandas as pd
from tqdm import tqdm
from pdf_extractor import extract_invoice_data, process_pdfs
from excel_processor import load_excel
from reconciler import reconcile
from json_builder import build_json
import warnings
warnings.simplefilter("ignore")

def main():
    # 1) procesar PDFs
    pdf_invoices = []
    errores = []
    total_files = 0
    for file in tqdm(os.listdir("Invoices")):
        if file.lower().endswith(".pdf"):
            full_path = os.path.join("Invoices", file)
            total_files += 1  
            data = extract_invoice_data(full_path)

            if data is None:
                print(f"❌ No se extrajo data de: {file}")
            else:
                pdf_invoices.append(data)


    pdf_df = pd.DataFrame(pdf_invoices)
    print(f"Total facturas PDF válidas: {len(pdf_df)} (de {total_files} archivos)")
    
    # Forzar tipos de datos para evitar conversión a None
    pdf_df['moneda'] = pdf_df['moneda'].fillna('COP')
    pdf_df['fecha_final'] = pdf_df['fecha_final'].fillna('')
    
    # Debug para verificar fechas y moneda en el DataFrame
    print("DEBUG - Muestra de fechas en PDF DataFrame:")
    # Usar los nuevos nombres definidos en el extractor
    pdf_df['fecha_final'] = pdf_df['fecha_final'].fillna('')
    pdf_df['fecha_inicio'] = pdf_df['fecha_inicio'].fillna('') # Agrega esta línea
    print(f"moneda: {pdf_df['moneda'].head(3).tolist()}")
    
    # Debug para verificar tipos de datos en el DataFrame
    print("DEBUG - Tipos de datos en PDF DataFrame:")
    print(f"fecha_inicio dtype: {pdf_df['fecha_inicio'].dtype}")
    print(f"fecha_final dtype: {pdf_df['fecha_final'].dtype}")
    print(f"moneda dtype: {pdf_df['moneda'].dtype}")

    # 2) cargar excel
    excel_path = "YCO01 - AP LISTING 20260104 con nit.xlsx"
    excel_df = load_excel(excel_path)

    # eliminar filas basura y resetear
    excel_df = excel_df.dropna(how="all").reset_index(drop=True)
    # filtrar filas con nit y invoice id si existen
    if "NIT" in excel_df.columns and any("Invoice" in str(c) for c in excel_df.columns):
        # already filtered in load_excel, but extra safety
        excel_df = excel_df[excel_df["nit_normalized"].notna()].reset_index(drop=True)

    print(f"Total facturas Excel limpias: {len(excel_df)}")
    print(pdf_df.columns)
    print(excel_df.columns)


    # --- 3. RECONCILIACIÓN ---
    print("\n Iniciando reconciliación...")
    merged_df, resultados_conciliacion = reconcile(pdf_df, excel_df)
    
    # Debug para verificar datos después del reconciliador
    print("DEBUG - Muestra de datos después de reconciliar:")
    print(f"fecha_inicio: {merged_df['fecha_inicio'].head(3).tolist()}")
    print(f"fecha_final: {merged_df['fecha_final'].head(3).tolist()}")
    print(f"moneda: {merged_df['moneda_pdf'].head(3).tolist() if 'moneda_pdf' in merged_df.columns else 'N/A'}")

    # --- 4. JSON ---
    print("\n Generando JSON...")
    total_pdf = len(pdf_df)
    total_excel = len(excel_df)
    build_json(merged_df, "output/conciliacion.json", errores, total_pdf, total_excel, resultados_conciliacion)

    print("Proceso finalizado correctamente.")

if __name__ == "__main__":
    main()
