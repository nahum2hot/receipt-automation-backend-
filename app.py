from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import os
import firebase_admin
from firebase_admin import firestore
import importlib
import json
import openai
from firebase_admin import credentials
import os
from dotenv import load_dotenv
import time

load_dotenv()
print("🧪 ENV Check - OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))
openai.api_key = os.getenv("OPENAI_API_KEY")

if openai.api_key:
    print("🔑 Loaded OpenAI Key:", openai.api_key[:8], "********")
else:
    print("❌ OpenAI key not found!")

firebase_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
firebase_dict = json.loads(firebase_json)
firebase_creds = credentials.Certificate(firebase_dict)

if not firebase_admin._apps:
    firebase_admin.initialize_app(firebase_creds)

import base64
from datetime import datetime
import re

app = Flask(__name__)


# Enhanced CORS configuration for Render deployment
CORS(app, 
     origins=[
         "http://localhost:3000",           # Local development
         "https://localhost:3000",          # Local HTTPS
         "https://your-frontend-domain.com" # Add your production frontend domain when ready
     ],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=[
         "Content-Type", 
         "Authorization", 
         "Access-Control-Allow-Credentials",
         "Access-Control-Allow-Origin"
     ],
     supports_credentials=True,
     max_age=86400
)

# Backup CORS headers for Render
@app.after_request
def after_request(response):
    origin = request.headers.get('Origin')
    if origin and ('localhost:3000' in origin or origin.startswith('http://localhost:3000')):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,Access-Control-Allow-Credentials'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

def load_extractor(profile_name):
    """
    Dynamically load an extractor module based on profile name
    
    Args:
        profile_name (str): Name of the extraction profile (e.g., 'grocery_ebt', 'restaurant_tip')
    
    Returns:
        module: The loaded extractor module with extract() function
    """
    try:
        # Import the module from extractors package
        module_name = f"extractors.{profile_name}"
        extractor_module = importlib.import_module(module_name)
        
        # Verify the module has an extract function
        if not hasattr(extractor_module, 'extract'):
            raise AttributeError(f"Extractor module '{profile_name}' missing extract() function")
        
        print(f"✅ Successfully loaded extractor: {profile_name}")
        return extractor_module
    
    except ImportError as e:
        print(f"❌ Failed to import extractor '{profile_name}': {e}")
        # Fallback to basic extractor
        try:
            basic_module = importlib.import_module("extractors.basic")
            print(f"🔄 Falling back to basic extractor")
            return basic_module
        except ImportError:
            raise Exception(f"Critical error: Cannot load basic extractor fallback")
    
    except AttributeError as e:
        print(f"❌ Extractor module error: {e}")
        raise Exception(f"Extractor '{profile_name}' is invalid: {e}")

def get_user_profile(user_id):
    """
    Fetch user's extraction profile from Firestore
    
    Args:
        user_id (str): Firebase UID of the user
    
    Returns:
        tuple: (user_data_dict, extraction_profile_string)
    """
    try:
        db = firestore.client()
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise Exception(f"User '{user_id}' not found in Firestore")
        
        user_data = user_doc.to_dict()
        extraction_profile = user_data.get("extractionProfile", "basic")
        
        print(f"👤 User {user_id} profile: {extraction_profile}")
        return user_data, extraction_profile
    
    except Exception as e:
        print(f"❌ Error fetching user profile: {e}")
        raise

def extract_json_from_content(content):
    """Extract JSON from GPT response content"""
    try:
        # First try direct parsing
        return json.loads(content)
    except json.JSONDecodeError:
        # If that fails, try to extract JSON from text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("No valid JSON found in content")

@app.route('/health', methods=['GET', 'OPTIONS'])
@cross_origin()
def health_check():
    return jsonify({
        "status": "healthy",
        "cors_enabled": True,
        "origin": request.headers.get('Origin', 'None'),
        "method": request.method
    }), 200

@app.route('/upload-receipt', methods=['POST', 'OPTIONS'])
@cross_origin(origins=['http://localhost:3000', 'https://localhost:3000'])
def upload_receipt():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response

    try:
        start = time.time()
        # 1. Validate request
        if 'image' not in request.files:
            return jsonify({
                "success": False,
                "error": "No image file provided"
            }), 400

        file = request.files['image']
        user_id = request.form.get('userId')

        if not user_id:
            return jsonify({
                "success": False,
                "error": "userId is required"
            }), 400

        if file.filename == '':
            return jsonify({
                "success": False,
                "error": "No file selected"
            }), 400

        print(f"🔄 Processing receipt for user: {user_id}")

        # 2. Get user's extraction profile from Firestore
        try:
            user_data, extraction_profile = get_user_profile(user_id)
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to fetch user profile: {str(e)}"
            }), 404

        # 3. Process image with OpenAI Vision (OCR)
        image_data = file.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        print(f"🤖 Calling OpenAI Vision API...")
        
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a receipt data extraction assistant. Analyze the receipt image and return ONLY a raw JSON object with no markdown formatting, no code blocks, no extra text. The JSON must be valid and parseable. Use exactly these field names: total_sales, tax, cash, timestamp. If a field cannot be found, use 0 for numbers or empty string for text."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract the following data from this receipt and return ONLY raw JSON: total_sales (number), tax (number), cash (number), timestamp (string). Return nothing but the JSON object."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300,
            temperature=0
        )
        print("OpenAI time:", time.time() - start)

        if response is None:
            return jsonify({
                "success": False,
                "error": "No response from OpenAI Vision"
            }), 500

        # 4. Parse OCR response
        raw_response = response.choices[0].message.content.strip()
        basic_receipt_data = extract_json_from_content(raw_response)

        # Ensure all expected fields are present
        required_fields = ['total_sales', 'tax', 'cash', 'timestamp']
        for field in required_fields:
            if field not in basic_receipt_data:
                basic_receipt_data[field] = 0 if field != 'timestamp' else ''

        print(f"📄 Basic OCR data: {basic_receipt_data}")

        # 5. Load and apply the appropriate extractor module
        try:
            extractor_module = load_extractor(extraction_profile)
            
            # Convert OCR data to text for the extractor
            ocr_text = json.dumps(basic_receipt_data)
            
            print(f"🔧 Running {extraction_profile} extractor...")
            
            # Call the extract function from the loaded module
            enhanced_data = extractor_module.extract(ocr_text)
            
            # Merge the enhanced data with basic OCR data
            final_receipt_data = {**basic_receipt_data, **enhanced_data}
            
        except Exception as e:
            print(f"❌ Extractor error: {e}")
            # Fallback to basic OCR data if extractor fails
            final_receipt_data = basic_receipt_data
            final_receipt_data['extraction_error'] = str(e)

        # 6. Add metadata
        final_receipt_data.update({
            'created_at': firestore.SERVER_TIMESTAMP,
            'upload_timestamp': datetime.now().isoformat(),
            'userId': user_id,
            'extractionProfile': extraction_profile,
            'businessName': user_data.get('businessName', ''),
            'tier': user_data.get('tier', 'basic')
        })

        print(f"📊 Final receipt data: {final_receipt_data}")

        # 7. Save to Firestore
        db = firestore.client()
        doc_ref = db.collection('receipts').add(final_receipt_data)
        document_id = doc_ref[1].id

        # 8. Prepare response (remove non-serializable fields)
        serializable_data = {k: v for k, v in final_receipt_data.items() if k != 'created_at'}

        print("Total time:", time.time() - start)
        return jsonify({
            "success": True,
            "message": "Receipt processed successfully",
            "data": serializable_data,
            "document_id": document_id,
            "extraction_profile_used": extraction_profile
        }), 200

    except Exception as e:
        print(f"❌ Upload receipt error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/')
def index():
    return """
    <h2>Welcome to the Safe Flow Receipt Automation Backend</h2>
    <p><a href="http://localhost:3000/signup">Signup</a> | <a href="http://localhost:3000/login">Login</a></p>
    """

# Route to test Firestore access using Admin SDK
@app.route('/test-firestore')
def test_firestore():
    try:
        db = firestore.client()
        test_ref = db.collection('users').limit(1)
        docs = test_ref.stream()

        for doc in docs:
            return jsonify({
                "success": True,
                "doc_id": doc.id,
                "doc_data": doc.to_dict()
            })

        return jsonify({"success": True, "message": "No documents found"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# New route to test extractors
@app.route('/test-extractor/<profile_name>')
def test_extractor(profile_name):
    """Test route to verify extractors are working"""
    try:
        extractor_module = load_extractor(profile_name)
        
        # Test with sample data
        sample_data = '{"total_sales": 45.67, "tax": 3.21, "cash": 50.00, "timestamp": "2025-01-15 14:30:00"}'
        result = extractor_module.extract(sample_data)
        
        return jsonify({
            "success": True,
            "profile": profile_name,
            "sample_input": sample_data,
            "extractor_output": result
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "profile": profile_name,
            "error": str(e)
        }), 500
        
@app.route("/test-delay")
def test_delay():
    import time
    time.sleep(45)
    return {"status": "done"}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)