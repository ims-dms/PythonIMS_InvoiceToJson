"""Minimal API test to isolate the issue"""
import sys
sys.path.insert(0, r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython')

print("Importing dependencies...")
try:
    from fastapi import FastAPI, Form, File, UploadFile
    print("✓ FastAPI imported")
    
    from db_connection import get_connection
    print("✓ db_connection imported")
    
    from token_manager import TokenManager
    print("✓ TokenManager imported")
    
    print("\nNow importing api module...")
    import api
    print("✓ api module imported successfully")
    
    print("\nChecking API app creation...")
    if hasattr(api, 'app'):
        print("✓ api.app exists")
        print(f"  Type: {type(api.app)}")
    
    print("\nAll imports successful!")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
