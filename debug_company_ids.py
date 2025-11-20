import sys
sys.path.insert(0, r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython')
from db_connection import get_connection

print('='*60)
print('Company / Token cross-check')
print('='*60)

conn = get_connection()
cur = conn.cursor()

# List companies if Company table exists
try:
    cur.execute("SELECT TOP 10 CompanyID, CompanyName FROM Company ORDER BY CompanyID")
    rows = cur.fetchall()
    print(f"Company table rows: {len(rows)} (showing up to 10)")
    for r in rows:
        print(f"  Company.CompanyID='{r[0]}' CompanyName='{r[1]}'")
except Exception as e:
    print(f"Company table query failed (may not exist): {e}")

# List tokens
try:
    cur.execute("SELECT TokenID, CompanyID, Status FROM [docUpload].TokenMaster ORDER BY CompanyID")
    rows = cur.fetchall()
    print(f"\nTokenMaster rows: {len(rows)}")
    for r in rows:
        print(f"  TokenID={r[0]} CompanyID='{r[1]}' Status='{r[2]}'")
except Exception as e:
    print(f"TokenMaster query failed: {e}")

# Check for NT001 specifically
for cid in ['NT001','NT047']:
    try:
        cur.execute("SELECT COUNT(*) FROM [docUpload].TokenMaster WHERE CompanyID = ?", (cid,))
        count_tok = cur.fetchone()[0]
    except:
        count_tok = 'err'
    try:
        cur.execute("SELECT COUNT(*) FROM Company WHERE CompanyID = ?", (cid,))
        count_comp = cur.fetchone()[0]
    except:
        count_comp = 'err'
    print(f"\nSummary for {cid}: TokenMaster={count_tok} Company={count_comp}")

conn.close()
print('\nDone.')
