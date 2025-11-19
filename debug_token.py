"""Debug the token lookup issue"""
import sys
sys.path.insert(0, r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython')

from db_connection import get_connection
from token_manager import TokenManager

# Test 1: Direct database query
print("=" * 60)
print("TEST 1: Direct database query")
print("=" * 60)

conn = get_connection()
cursor = conn.cursor()

# Check what companies have tokens
cursor.execute("SELECT TokenID, CompanyID, Status, ApiKey FROM TokenMaster")
tokens = cursor.fetchall()
print(f"\nTokens in database: {len(tokens)}")
for row in tokens:
    token_id, company_id, status, api_key = row
    print(f"  TokenID={token_id}, CompanyID='{company_id}', Status='{status}', ApiKey={api_key[:20]}...")

# Test 2: TokenManager.get_active_token()
print("\n" + "=" * 60)
print("TEST 2: TokenManager.get_active_token('NT047')")
print("=" * 60)

result = TokenManager.get_active_token('NT047', conn)
print(f"Result: {result}")

# Test 3: TokenManager.get_active_token() with different formats
print("\n" + "=" * 60)
print("TEST 3: Try different company IDs")
print("=" * 60)

test_cases = [
    'NT047',
    'NT047 ',
    ' NT047',
    'nt047',
    'NT047\n',
    'NT047\r'
]

for company_id in test_cases:
    result = TokenManager.get_active_token(company_id, conn)
    status = "SUCCESS" if result.get('success') else "FAILED"
    print(f"  '{repr(company_id)}' -> {status}")

conn.close()

print("\n" + "=" * 60)
print("TEST 4: Check API FormData parsing")
print("=" * 60)
print("Making a request to the API to see what CompanyID it receives...")

# Add logging to see what gets passed
from api import app
print("API app loaded successfully")
