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


    # 3) reconciliar
    merged = reconcile(pdf_df, excel_df)

    # 4) generar JSON
    total_pdf = len(pdf_df)
    total_excel = len(excel_df)
    os.makedirs("output", exist_ok=True)
    build_json(merged, "output/conciliacion.json", errores, total_pdf=total_pdf, total_excel=total_excel)

    print("Proceso finalizado correctamente.")

if __name__ == "__main__":
    main()
