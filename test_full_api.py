"""Test the complete API flow with token retrieval"""
import requests
import io
from pathlib import Path

# Check if there's a sample PDF or create a minimal one
test_pdf_path = r"C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython\test_sample.pdf"

# Create a minimal valid PDF if it doesn't exist
if not Path(test_pdf_path).exists():
    # Minimal PDF file (works but empty)
    pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF"""
    with open(test_pdf_path, 'wb') as f:
        f.write(pdf_content)
    print(f"[OK] Created minimal test PDF at {test_pdf_path}")

# Prepare the request
url = "http://127.0.0.1:8000/extract"
print(f"\nTesting {url}...")

# Open the test PDF file
with open(test_pdf_path, 'rb') as pdf_file:
    files = {
        'file': ('test.pdf', pdf_file, 'application/pdf')
    }
    data = {
        'companyID': 'NT047',
        'username': 'testuser',
        'extractFromLink': '0'
    }
    
    try:
        response = requests.post(url, files=files, data=data, timeout=30)
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body (first 1000 chars):")
        print(response.text[:1000])
        
        if "Token" in response.text and ("selected" in response.text or "error" in response.text):
            print("\n[SUCCESS] Token was successfully retrieved and API processed the request!")
        elif "No active token" in response.text:
            print("\n[FAILED] Still getting token error")
        else:
            print("\n[WARNING] Response received but format unclear")
            
    except requests.exceptions.Timeout:
        print("[WARNING] Request timed out - API may be processing")
    except Exception as e:
        print(f"[ERROR] {e}")
