"""Comprehensive diagnostics for token issue"""
import sys
sys.path.insert(0, r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython')

from db_connection import get_connection
from token_manager import TokenManager

print("=" * 70)
print("TOKEN SYSTEM DIAGNOSTICS")
print("=" * 70)

# 1. Check database connection
print("\n1. DATABASE CONNECTION:")
try:
    conn = get_connection()
    print("   [OK] Connected to database")
    
    # 2. Check TokenMaster table exists
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_NAME = 'TokenMaster'
    """)
    if cursor.fetchone():
        print("   [OK] TokenMaster table exists")
    else:
        print("   [ERROR] TokenMaster table not found!")
        sys.exit(1)
    
    # 3. Count tokens
    cursor.execute("SELECT COUNT(*) FROM TokenMaster")
    count = cursor.fetchone()[0]
    print(f"   [OK] {count} total tokens in database")
    
    # 4. List all tokens
    print("\n2. TOKENS IN DATABASE:")
    cursor.execute("""
        SELECT TokenID, CompanyID, CompanyName, Status, Provider, TotalTokenLimit
        FROM TokenMaster
        ORDER BY CompanyID
    """)
    tokens = cursor.fetchall()
    if tokens:
        for token in tokens:
            print(f"   TokenID={token[0]}: CompanyID='{token[1]}' ({token[2]}), Status={token[3]}, Provider={token[4]}, Limit={token[5]}")
    else:
        print("   [ERROR] NO TOKENS FOUND IN DATABASE!")
    
    # 5. Test TokenManager.get_active_token() for each company
    print("\n3. TOKEN RETRIEVAL TEST:")
    cursor.execute("SELECT DISTINCT CompanyID FROM TokenMaster")
    companies = [row[0] for row in cursor.fetchall()]
    
    for company in companies:
        result = TokenManager.get_active_token(company, conn)
        if result.get('success'):
            print(f"   [OK] {company}: Token {result.get('token_id')} retrieved successfully")
        else:
            print(f"   [ERROR] {company}: {result.get('message')}")
    
    # 6. Check appSetting.txt
    print("\n4. APPSETTING.TXT:")
    try:
        with open(r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython\appSetting.txt') as f:
            content = f.read().strip()
            if content and not content.startswith('GEMINI_API_KEY='):
                print(f"   [WARNING] Unexpected format: {content[:100]}")
            elif 'GEMINI_API_KEY=' in content:
                api_key = content.split('=')[1] if '=' in content else ''
                if api_key:
                    print(f"   [OK] Contains API key: {api_key[:30]}...")
                else:
                    print(f"   [WARNING] appSetting.txt has empty API key")
    except FileNotFoundError:
        print("   [INFO] appSetting.txt not found (using database instead)")
    
    conn.close()
    
except Exception as e:
    print(f"   [ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("RECOMMENDED ACTIONS:")
print("=" * 70)
if not tokens:
    print("1. ADD A TOKEN: Run 'python add_company_token.py'")
else:
    print(f"1. Use Company ID: '{companies[0]}' when calling the API")
    print("2. Or add a new company using 'python add_company_token.py'")

print("\nDONE!")
