import re
from datetime import datetime

def extract_fields(text: str) -> dict:
    try:
        total_sales = float(re.search(r"Total(?:\s+Amount)?\s*[:\-]?\s*\$?(\d+\.\d{2})", text, re.IGNORECASE).group(1))
    except:
        total_sales = 0

    try:
        tax = float(re.search(r"Tax\s*[:\-]?\s*\$?(\d+\.\d{2})", text, re.IGNORECASE).group(1))
    except:
        tax = 0

    try:
        cash = float(re.search(r"Cash\s*[:\-]?\s*\$?(\d+\.\d{2})", text, re.IGNORECASE).group(1))
    except:
        cash = 0

    try:
        credit = float(re.search(r"Credit\s*[:\-]?\s*\$?(\d+\.\d{2})", text, re.IGNORECASE).group(1))
    except:
        credit = 0

    try:
        ebt = float(re.search(r"EBT\s*[:\-]?\s*\$?(\d+\.\d{2})", text, re.IGNORECASE).group(1))
    except:
        ebt = 0

    try:
        timestamp_match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", text)
        timestamp = datetime.strptime(timestamp_match.group(1), "%m/%d/%Y").isoformat() if timestamp_match else ""
    except:
        timestamp = ""

    return {
        "total_sales": total_sales,
        "tax": tax,
        "cash": cash,
        "credit": credit,
        "ebt": ebt,
        "timestamp": timestamp
    }
