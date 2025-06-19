import re
from datetime import datetime

def extract_fields(text: str) -> dict:
    try:
        total_match = re.search(r"total\s*[:\-]?\s*\$?(\d+\.\d{2})", text, re.IGNORECASE)
        tax_match = re.search(r"tax\s*[:\-]?\s*\$?(\d+\.\d{2})", text, re.IGNORECASE)
        cash_match = re.search(r"cash\s*[:\-]?\s*\$?(\d+\.\d{2})", text, re.IGNORECASE)
        date_match = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})", text)

        total_sales = float(total_match.group(1)) if total_match else 0
        tax = float(tax_match.group(1)) if tax_match else 0
        cash = float(cash_match.group(1)) if cash_match else 0
        timestamp = date_match.group(1) if date_match else ""

        # Optional: Format timestamp for consistency
        try:
            dt_obj = datetime.strptime(timestamp, "%m/%d/%Y")
            timestamp = dt_obj.strftime("%m/%d/%Y")
        except:
            pass

        return {
            "total_sales": total_sales,
            "tax": tax,
            "cash": cash,
            "timestamp": timestamp
        }

    except Exception as e:
        print(f"[basic.py] Extraction error: {e}")
        return {
            "total_sales": 0,
            "tax": 0,
            "cash": 0,
            "timestamp": ""
        }
