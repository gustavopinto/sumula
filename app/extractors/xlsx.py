"""Extract text from Excel files using pandas."""
from pathlib import Path


def extract_xlsx(path: str | Path) -> list[dict]:
    """Return list of {sheet: str, row: int, text: str} dicts."""
    import pandas as pd

    results = []
    xl = pd.ExcelFile(str(path), engine="openpyxl")
    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name, header=None, dtype=str)
        for row_idx, row in df.iterrows():
            parts = [str(v).strip() for v in row if str(v).strip() and str(v).strip() != "nan"]
            if parts:
                results.append({
                    "sheet": str(sheet_name),
                    "row": int(row_idx) + 1,
                    "text": " | ".join(parts),
                })
    return results
