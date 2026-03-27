import pandas as pd
import os

DATA_DIR = "data"
LOG_FILE = os.path.join(DATA_DIR, "trades.csv")
EXCEL_FILE = os.path.join(DATA_DIR, "trades.xlsx")

def csv_to_excel():
    if not os.path.exists(LOG_FILE):
        print("CSV log file not found.")
        return
    df = pd.read_csv(LOG_FILE)
    df.to_excel(EXCEL_FILE, index=False)
    print(f"Excel saved at {EXCEL_FILE}")

if __name__ == "__main__":
    csv_to_excel()
