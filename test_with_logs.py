"""Test API and capture all logs"""
import subprocess
import time
import threading
import requests

# Start the API in a subprocess
print("Starting API server...")
api_process = subprocess.Popen(
    ['python', '-m', 'uvicorn', 'api:app', '--host', '127.0.0.1', '--port', '8000', '--log-level', 'debug'],
    cwd=r'C:\BzuMah\Office\Development\WebPosVariant\OCR\FinalPython',
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

# Function to read and print output
def read_output():
    for line in api_process.stdout:
        print(f"[API] {line.rstrip()}")

# Start reading output in background thread
output_thread = threading.Thread(target=read_output, daemon=True)
output_thread.start()

# Wait for API to start
time.sleep(3)

print("\n" + "="*70)
print("Making test request...")
print("="*70)

# Make a test request
form_data = {
    'companyID': 'NT047',
    'username': 'testuser',
    'extractFromLink': '0'
}

try:
    response = requests.post(
        'http://127.0.0.1:8000/extract',
        data=form_data,
        timeout=10
    )
    print(f"\n[TEST] Status: {response.status_code}")
    print(f"[TEST] Response: {response.json()}")
except Exception as e:
    print(f"[TEST] Error: {e}")

time.sleep(2)
print("\n" + "="*70)
print("Stopping API...")
print("="*70)
api_process.terminate()
api_process.wait(timeout=5)
