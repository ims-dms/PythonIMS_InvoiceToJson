"""Test with all available companies"""
import sys
sys.path.insert(0, r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython')

from db_connection import get_connection
from token_manager import TokenManager

conn = get_connection()
cursor = conn.cursor()

# Get all companies with tokens
cursor.execute("SELECT DISTINCT CompanyID FROM TokenMaster ORDER BY CompanyID")
companies = [row[0] for row in cursor.fetchall()]

print("Available companies with tokens:")
for company in companies:
    print(f"  - '{company}'")

print("\nTesting token retrieval for each company:")
for company in companies:
    result = TokenManager.get_active_token(company, conn)
    status = "OK" if result.get('success') else "FAILED"
    print(f"  '{company}': {status}")
    if not result.get('success'):
        print(f"    Error: {result.get('message')}")

# Also test with appSetting.txt
print("\n" + "="*60)
print("Checking appSetting.txt...")
try:
    with open(r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython\appSetting.txt') as f:
        content = f.read()
        print(f"Content: {content[:200]}")
except Exception as e:
    print(f"Error reading appSetting.txt: {e}")

conn.close()
