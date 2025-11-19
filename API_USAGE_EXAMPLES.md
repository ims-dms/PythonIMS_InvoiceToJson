# API Request Examples and Usage Guide

## Overview
This document provides examples of how to call the updated `/extract` endpoint with token management system.

---

## Basic Request

### cURL Example
```bash
curl -X POST http://localhost:8000/extract \
  -F "file=@invoice.pdf" \
  -F "companyID=NT047" \
  -F "username=bzumah" \
  -F "branch=RUB"
```

### Python Example
```python
import requests

url = "http://localhost:8000/extract"
files = {'file': open('invoice.pdf', 'rb')}
data = {
    'companyID': 'NT047',
    'username': 'bzumah',
    'branch': 'RUB',
    'licenceID': 'LIC001'
}

response = requests.post(url, files=files, data=data)
result = response.json()

if result['status'] == 'ok':
    print("Success!")
    print(f"Invoice #: {result['data']['invoice_no']}")
else:
    print(f"Error: {result['message']}")
```

### JavaScript/Fetch Example
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('companyID', 'NT047');
formData.append('username', 'bzumah');
formData.append('branch', 'RUB');
formData.append('licenceID', 'LIC001');

fetch('http://localhost:8000/extract', {
    method: 'POST',
    body: formData
})
.then(response => response.json())
.then(result => {
    if (result.status === 'ok') {
        console.log('Success!', result.data);
    } else {
        console.error('Error:', result.message);
    }
});
```

---

## Advanced Requests

### With Custom Database Connection
```bash
curl -X POST http://localhost:8000/extract \
  -F "file=@invoice.pdf" \
  -F "companyID=NT047" \
  -F "username=bzumah" \
  -F "branch=RUB" \
  -F "connection_params={\"server\":\"localhost\",\"database\":\"mydb\",\"user\":\"admin\",\"password\":\"pass\"}"
```

### From URL Link
```bash
curl -X POST http://localhost:8000/extract \
  -F "companyID=NT047" \
  -F "username=bzumah" \
  -F "branch=RUB" \
  -F "extractFromLink=1" \
  -F "pdf_url=https://example.com/invoice.pdf"
```

### Python with Custom Connection
```python
import json
import requests

url = "http://localhost:8000/extract"
files = {'file': open('invoice.pdf', 'rb')}

conn_params = {
    "server": "db.example.com",
    "database": "OCR_DB",
    "user": "ocr_user",
    "password": "secure_pass"
}

data = {
    'companyID': 'NT047',
    'username': 'bzumah',
    'branch': 'RUB',
    'licenceID': 'LIC001',
    'connection_params': json.dumps(conn_params)
}

response = requests.post(url, files=files, data=data)
print(response.json())
```

---

## Response Examples

### Successful Response
```json
{
  "status": "ok",
  "message": "Invoice processed successfully",
  "data": {
    "order_no": "ORD-2025-001",
    "invoice_no": "INV-2025-5678",
    "delivery_note": "DN-001",
    "vehicle_no": "BA-1-A-1234",
    "transporter": "Fast Logistics",
    "date": "2025-11-19",
    "dealer_name": "Local Dealer",
    "pws_no": "PWS123",
    "company_name": "RUBI TRADERS Pvt ltd",
    "transaction_type": "Sale",
    "transaction_date": "2025-11-19",
    "due_date": "2025-12-19",
    "invoice_miti": "2082-08-04",
    "invoice_date": "2025-11-19",
    "products": [
      {
        "sku": "PROD-001",
        "sku_code": "SKU001",
        "quantity": 100,
        "shortage": 5,
        "breakage": 2,
        "leakage": 0,
        "batch": "BATCH2025",
        "sno": "001",
        "rate": 250.00,
        "discount": 10.00,
        "mrp": 300.00,
        "vat": 30.00,
        "hscode": "8471.30",
        "altQty": 100,
        "unit": "BOX"
      }
    ]
  }
}
```

### Token Expired Response
```json
{
  "status": "error",
  "message": "Your AI token has expired. Please renew your subscription.",
  "data": null
}
```

### Retry Failed Response
```json
{
  "status": "error",
  "message": "Failed to process invoice",
  "data": {
    "actual_error": "Service temporarily unavailable after 3 retries"
  }
}
```

### Invalid File Response
```json
{
  "status": "error",
  "message": "Failed to convert PDF",
  "data": {
    "actual_error": "Unsupported PDF format"
  }
}
```

### Missing Parameters Response
```json
{
  "status": "error",
  "message": "Please provide both companyID and username.",
  "data": null
}
```

---

## Error Scenarios and Handling

### Scenario 1: Invalid/Corrupt PDF
```python
# This will NOT retry - error is not retryable
# Response comes immediately

{
  "status": "error",
  "message": "Failed to convert PDF",
  "data": {"actual_error": "PDF is corrupted"}
}
```

### Scenario 2: API Rate Limited
```python
# This WILL retry with exponential backoff
# Attempt 1: Wait 1 second, retry
# Attempt 2: Wait 2 seconds, retry
# Attempt 3: Wait 4 seconds, retry
# Then show error

{
  "status": "error",
  "message": "Failed to process invoice",
  "data": {"actual_error": "Rate limit exceeded after 3 retries"}
}
```

### Scenario 3: Token Expired
```python
# This is checked BEFORE processing
# No API call made, immediate response

{
  "status": "error",
  "message": "Your AI token has expired. Please renew your subscription.",
  "data": null
}
```

---

## Monitoring & Debugging

### Check Recent Requests
```sql
-- View recent API calls and token usage
SELECT TOP 20
    ul.UsageID,
    ul.Branch,
    ul.RequestedBy,
    ul.TotalTokensUsed,
    ul.LoggedAt,
    tm.CompanyName,
    tm.Status
FROM TokenUsageLogs ul
JOIN TokenMaster tm ON ul.TokenID = tm.TokenID
ORDER BY ul.LoggedAt DESC;
```

### Check for Retries
```sql
-- View retry attempts
SELECT TOP 50
    ra.RetryID,
    ra.CompanyID,
    ra.Attempt,
    ra.ErrorMessage,
    ra.Timestamp
FROM RetryAttempts ra
ORDER BY ra.Timestamp DESC;
```

### Check Error Logs
```sql
-- View recent errors
SELECT TOP 100
    LogID,
    Timestamp,
    LogLevel,
    Message,
    Module,
    FunctionName
FROM ApplicationLogs
WHERE LogLevel IN ('ERROR', 'WARNING')
ORDER BY Timestamp DESC;
```

### Check Token Status
```sql
-- View current token status for all companies
SELECT 
    tm.CompanyID,
    tm.CompanyName,
    tm.Status,
    ts.TotalUsedTokens,
    ts.TotalRemainingTokens,
    CAST(ts.TotalUsedTokens * 100.0 / tm.TotalTokenLimit AS DECIMAL(5,2)) as UtilizationPercent
FROM TokenMaster tm
LEFT JOIN TokenUsageSummary ts ON tm.TokenID = ts.TokenID
ORDER BY tm.CompanyID;
```

---

## Postman Collection Example

### Environment Variables
```json
{
  "base_url": "http://localhost:8000",
  "company_id": "NT047",
  "username": "bzumah",
  "branch": "RUB"
}
```

### Request Configuration
```
Method: POST
URL: {{base_url}}/extract

Headers:
- Content-Type: multipart/form-data (auto-set)

Body (form-data):
- file (type: File) - Select PDF or image
- companyID (type: Text) - {{company_id}}
- username (type: Text) - {{username}}
- branch (type: Text) - {{branch}}
- licenceID (type: Text) - LIC001 (optional)

Pre-request Script:
(None needed)

Tests:
pm.test("Status code is 200", function() {
    pm.response.to.have.status(200);
});

pm.test("Response has correct structure", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('status');
    pm.expect(jsonData).to.have.property('message');
});
```

---

## Rate Limiting & Retry Strategy

### Exponential Backoff Example
```
Attempt 1 (immediate)
  ↓ Fails
Attempt 2 (wait 1.2 seconds with jitter)
  ↓ Fails
Attempt 3 (wait 2.4 seconds with jitter)
  ↓ Fails
Attempt 4 (wait 4.8 seconds with jitter)
  ↓ Return error
```

### Non-Retryable Errors (Immediate Response)
- Invalid PDF format
- Corrupted file
- Unsupported file type
- Malformed data
- Invalid parameters

### Retryable Errors (With Retries)
- Connection timeout
- Rate limit exceeded
- Service temporarily unavailable
- Internal server error (500, 502, 503, 504)
- Any "try again" message

---

## Performance Tips

### 1. Batch Processing
```python
# Process multiple invoices sequentially
invoices = ['invoice1.pdf', 'invoice2.pdf', 'invoice3.pdf']

for invoice_file in invoices:
    files = {'file': open(invoice_file, 'rb')}
    data = {'companyID': 'NT047', 'username': 'system', 'branch': 'RUB'}
    
    response = requests.post(url, files=files, data=data)
    if response.json()['status'] == 'ok':
        print(f"✓ {invoice_file} processed")
    else:
        print(f"✗ {invoice_file} failed")
    
    time.sleep(1)  # Avoid rate limiting
```

### 2. Check Token Status First
```python
# Check if token is available before processing
status_response = requests.get('http://localhost:8000/token/status?companyID=NT047')

if status_response.json()['has_error']:
    print(f"Cannot process: {status_response.json()['message']}")
else:
    # Safe to process
    response = requests.post(url, files=files, data=data)
```

### 3. Monitor Token Usage
```python
# Check remaining tokens before processing large batch
summary_response = requests.get('http://localhost:8000/token/summary?companyID=NT047')
remaining = summary_response.json()['remaining_tokens']

if remaining < 100000:  # Threshold
    print(f"Warning: Only {remaining} tokens remaining")
```

---

## Integration Examples

### Django Example
```python
# views.py
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import requests

@require_http_methods(["POST"])
def process_invoice(request):
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file provided'}, status=400)
    
    file = request.FILES['file']
    url = 'http://localhost:8000/extract'
    
    response = requests.post(
        url,
        files={'file': file},
        data={
            'companyID': request.POST.get('companyID'),
            'username': request.user.username,
            'branch': request.POST.get('branch', 'Default')
        }
    )
    
    return JsonResponse(response.json())
```

### Flask Example
```python
# app.py
from flask import Flask, request, jsonify
import requests

@app.route('/api/process-invoice', methods=['POST'])
def process_invoice():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    url = 'http://localhost:8000/extract'
    
    response = requests.post(
        url,
        files={'file': file},
        data={
            'companyID': request.form.get('companyID'),
            'username': request.form.get('username'),
            'branch': request.form.get('branch', 'Default')
        }
    )
    
    return jsonify(response.json())
```

### FastAPI Client Example
```python
# client.py
import httpx
from pathlib import Path

async def process_invoice(file_path: str, company_id: str, username: str):
    async with httpx.AsyncClient() as client:
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'companyID': company_id,
                'username': username,
                'branch': 'Default'
            }
            
            response = await client.post(
                'http://localhost:8000/extract',
                files=files,
                data=data
            )
            
            return response.json()
```

---

## Troubleshooting Common Issues

### "No active token found"
```python
# Solution: Verify token exists
import sqlite3
conn = sqlite3.connect('your_database.db')
cursor = conn.cursor()
cursor.execute("SELECT * FROM TokenMaster WHERE CompanyID = ? AND Status = 'Active'", ('NT047',))
result = cursor.fetchone()
if not result:
    print("Token not found. Insert one using setup_database.sql")
```

### "Service temporarily unavailable"
```python
# This is retryable - API will retry automatically
# Check ApplicationLogs for retry attempts
```

### "Invalid file format"
```python
# This is NOT retryable - show error immediately
# Verify file is valid PDF or image
# Check file size (should be < 100MB typical)
```

---

**Note:** All examples assume API is running on `http://localhost:8000`. Adjust for your deployment URL.

