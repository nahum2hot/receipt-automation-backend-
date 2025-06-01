import os
import base64
import json
from flask import Flask, request, jsonify
from flask_cors import CORS  # 🟢 Add this
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()

app = Flask(__name__)
CORS(app)  # 🟢 Add this to enable CORS for **all** routes

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
service_account_path = os.environ.get("SERVICE_ACCOUNT_KEY_PATH", "service_account_key.json")
creds = ServiceAccountCredentials.from_json_keyfile_name(service_account_path, scope)
gc = gspread.authorize(creds)
spreadsheet = gc.open("Daily Sales Tracker  ")  # Note: trailing spaces!

@app.route("/upload-receipt", methods=["POST"])
def upload_receipt():
    if "receipt" not in request.files:
        return jsonify({"error": "No receipt file provided"}), 400

    receipt_file = request.files["receipt"]
    image_bytes = receipt_file.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = """
You are an assistant that extracts structured data from printed receipts.

From this receipt image, extract the following values as JSON. 
If a value is not visible or clearly labeled, return it as null.

Output only JSON in this format:

{
  "TOTAL SALES": "...",
  "CASH": "...",
  "CREDIT": "...",
  "EBT": "...",
  "TAX": "...",
  "PROFIT": "...",
  "COST": "...",
  "TOTAL TICKETS": "...",
  "AVERAGE TICKET": "..."
}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        temperature=0.2
    )

    gpt_content = response.choices[0].message.content.strip()
    if gpt_content.startswith("```"):
        gpt_content = gpt_content.strip("`").strip()
        if gpt_content.lower().startswith("json"):
            gpt_content = gpt_content[4:].strip()

    try:
        gpt_result = json.loads(gpt_content)
    except json.JSONDecodeError as e:
        return jsonify({"error": "Failed to parse GPT response", "details": str(e)}), 500

    sheet = spreadsheet.worksheet("Form Responses 1")
    timestamp = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
    new_row = [
        timestamp,
        "",
        gpt_result.get("TOTAL SALES", ""),
        gpt_result.get("CASH", ""),
        gpt_result.get("EBT", ""),
        gpt_result.get("TAX", ""),
        gpt_result.get("PROFIT", ""),
        gpt_result.get("COST", ""),
        ""
    ]
    sheet.append_row(new_row)

    return jsonify({
        "message": "✅ Data extracted and saved to Google Sheets!",
        "data": gpt_result
    }), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000) 