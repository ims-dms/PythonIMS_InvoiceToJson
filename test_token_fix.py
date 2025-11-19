#!/usr/bin/env python
from token_manager import TokenManager

print('Testing token retrieval for NT047...')
result = TokenManager.get_active_token('NT047')
if result.get('success'):
    print('✅ SUCCESS! Token retrieved:')
    print(f'   - Token ID: {result.get("token_id")}')
    print(f'   - Company: NT047')
    print(f'   - Provider: {result.get("provider")}')
    print(f'   - Status: {result.get("status")}')
    print(f'   - API Key: {result.get("api_key")[:20]}...')
else:
    print('❌ FAILED:')
    print(f'   - Error: {result.get("message")}')
