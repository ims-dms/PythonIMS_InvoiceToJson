"""
Database Connection Diagnostic Script
Tests SQL Server connection and helps troubleshoot authentication issues
"""
import json
import pyodbc
from encryption_util import decrypt_if_encrypted

def test_connection():
    print("=" * 70)
    print("SQL Server Connection Diagnostics")
    print("=" * 70)
    
    # Read configuration
    print("\n1. Reading DBConnection.txt...")
    with open('DBConnection.txt', 'r') as f:
        lines = f.readlines()
        json_content = ''.join(line for line in lines if not line.strip().startswith('#'))
        config = json.loads(json_content.strip())
    
    print("   ✓ Configuration loaded")
    
    # Extract and decrypt password
    print("\n2. Processing credentials...")
    server = config.get("SERVER", config.get("server"))
    database = config.get("DATABASE", config.get("database"))
    user = config.get("USER", config.get("user"))
    encrypted_password = config.get("PASSWORD", config.get("password"))
    
    print(f"   Server: {server}")
    print(f"   Database: {database}")
    print(f"   User: {user}")
    print(f"   Encrypted Password: {encrypted_password}")
    
    # Decrypt password
    decrypted_password = decrypt_if_encrypted(encrypted_password)
    print(f"   Decrypted Password: {'*' * len(decrypted_password)} (length: {len(decrypted_password)})")
    
    # Test available drivers
    print("\n3. Checking available ODBC drivers...")
    drivers = [d for d in pyodbc.drivers() if 'SQL Server' in d]
    if drivers:
        for driver in drivers:
            print(f"   ✓ {driver}")
    else:
        print("   ✗ No SQL Server drivers found!")
        return
    
    # Build connection string
    print("\n4. Testing connection with ODBC Driver 17...")
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={decrypted_password}"
    )
    
    try:
        connection = pyodbc.connect(conn_str, timeout=5)
        print("   ✓ Connection successful!")
        
        # Test query
        cursor = connection.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        print(f"\n   SQL Server Version:")
        print(f"   {version[:100]}...")
        
        cursor.close()
        connection.close()
        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED - Database connection is working!")
        print("=" * 70)
        
    except pyodbc.Error as e:
        print(f"   ✗ Connection failed!")
        print(f"\n   Error Details:")
        print(f"   {e}")
        
        print("\n" + "=" * 70)
        print("TROUBLESHOOTING SUGGESTIONS:")
        print("=" * 70)
        print("\n1. Check SQL Server Authentication Mode:")
        print("   - Open SQL Server Management Studio (SSMS)")
        print("   - Right-click server → Properties → Security")
        print("   - Ensure 'SQL Server and Windows Authentication mode' is selected")
        print("   - Restart SQL Server service after changing")
        
        print("\n2. Verify 'sa' account status:")
        print("   - In SSMS, expand Security → Logins")
        print("   - Right-click 'sa' → Properties")
        print("   - Status page: Ensure 'Login' is Enabled")
        
        print("\n3. Reset 'sa' password:")
        print("   - In SSMS: ALTER LOGIN sa WITH PASSWORD = 'YourNewPassword'")
        print("   - Then update DBConnection.txt with new encrypted password")
        
        print("\n4. Test with Windows Authentication:")
        print("   - Temporarily change DBConnection.txt to use Windows auth")
        print("   - Remove USER and PASSWORD, add: \"Trusted_Connection\": \"yes\"")
        
        print("\n5. Check SQL Server service:")
        print("   - Services.msc → SQL Server (SQLEXPRESS)")
        print("   - Ensure it's running")
        
        print("\n6. Generate new encrypted password:")
        print("   Run: python encryption_util.py")
        print("   Enter your actual password to get encrypted version")
        print("=" * 70)

if __name__ == "__main__":
    try:
        test_connection()
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
