from db_connection import get_connection

print("Testing database query...")
try:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check all tokens
    print("\n1. Checking all tokens in TokenMaster:")
    cursor.execute("SELECT TokenID, CompanyID, Status FROM TokenMaster")
    rows = cursor.fetchall()
    print(f"   Total rows: {len(rows)}")
    for row in rows:
        print(f"   - TokenID: {row[0]}, CompanyID: {row[1]}, Status: {row[2]}")
    
    # Check specific company
    print("\n2. Checking tokens for NT047:")
    cursor.execute("SELECT TokenID, CompanyID, Status FROM TokenMaster WHERE CompanyID = ?", ('NT047',))
    rows = cursor.fetchall()
    print(f"   Rows found: {len(rows)}")
    for row in rows:
        print(f"   - TokenID: {row[0]}, CompanyID: {row[1]}, Status: {row[2]}")
    
    # Check active tokens for NT047
    print("\n3. Checking ACTIVE tokens for NT047:")
    cursor.execute("SELECT TokenID, CompanyID, Status FROM TokenMaster WHERE CompanyID = ? AND Status = ?", ('NT047', 'Active'))
    rows = cursor.fetchall()
    print(f"   Rows found: {len(rows)}")
    for row in rows:
        print(f"   - TokenID: {row[0]}, CompanyID: {row[1]}, Status: {row[2]}")
    
    cursor.close()
    conn.close()
    print("\n✅ Database connection successful")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
