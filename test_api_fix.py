"""Test the API token retrieval fix"""
import requests
import time

time.sleep(2)  # Wait for API to fully start

# Test data
url = "http://127.0.0.1:8000/extract"

# Create a test payload with form data
# Using a minimal test without actual file
data = {
    'companyID': 'NT047',
    'username': 'testuser',
    'extractFromLink': '0'
}

print("Testing API /extract endpoint...")
print(f"URL: {url}")
print(f"Data: {data}")

try:
    # Just send form data without file
    response = requests.post(url, data=data, timeout=10)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    # Check if we got past the token error
    if "No active token found" in response.text:
        print("\n❌ FAILED: Still getting 'No active token found' error")
    elif "Token" in response.text and "selected" in response.text:
        print("\n✅ SUCCESS: Token was successfully retrieved!")
    else:
        print("\n⚠️ Different response - check output above")
        
except Exception as e:
    print(f"Error: {e}")
