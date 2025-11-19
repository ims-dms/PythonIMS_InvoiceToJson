from token_manager import TokenManager
import logging

logging.basicConfig(level=logging.DEBUG)

print("Testing TokenManager.get_active_token()...")
print("\n1. Testing with 'NT047':")
result = TokenManager.get_active_token('NT047')
print(f"   Result: {result}")

print("\n2. Testing with different cases:")
for test_id in ['NT047', 'nt047', 'NT047 ', ' NT047']:
    result = TokenManager.get_active_token(test_id)
    print(f"   Input: '{test_id}' -> Success: {result.get('success')}")
