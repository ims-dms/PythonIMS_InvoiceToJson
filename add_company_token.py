"""Add a new company token to the database"""
import sys
sys.path.insert(0, r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython')

from db_connection import get_connection

print("=" * 70)
print("ADD NEW COMPANY TOKEN")
print("=" * 70)

# Get user input
company_id = input("\nEnter Company ID (e.g., ABC001): ").strip()
company_name = input("Enter Company Name (e.g., ABC Corp): ").strip()
api_key = input("Enter Gemini API Key: ").strip()

if not all([company_id, company_name, api_key]):
    print("ERROR: All fields are required!")
    sys.exit(1)

print(f"\nAdding token for company '{company_id}'...")

conn = get_connection()
cursor = conn.cursor()

try:
    cursor.execute("""
        INSERT INTO [docUpload].TokenMaster (CompanyID, CompanyName, ApiKey, Provider, TotalTokenLimit, Status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (company_id, company_name, api_key, 'Gemini', 100000, 'Active'))
    conn.commit()
    print("SUCCESS! Token added to database.")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    cursor.close()
    conn.close()

# Show all companies
print("\n" + "=" * 70)
print("Current companies in database:")
print("=" * 70)
conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT TokenID, CompanyID, CompanyName, Status FROM [docUpload].TokenMaster")
for row in cursor.fetchall():
    print(f"  TokenID={row[0]}, CompanyID='{row[1]}', Name='{row[2]}', Status={row[3]}")
conn.close()
