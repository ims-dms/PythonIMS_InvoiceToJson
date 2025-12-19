IMS Software Tax Invoice Processor

Installation
------------

To install the required dependencies, run:

```
pip install -r requirements.txt
```

Running the Application
-----------------------

To start the FastAPI server with auto-reload, run:

```
python -m uvicorn api:app --reload


#Virtual Running - OK
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000

CORS Configuration
------------------

The API enables dynamic CORS. Configure allowed origins via environment variables:

- CORS_ALLOW_ORIGINS: Comma-separated list of exact origins
	Example (PowerShell):
	$env:CORS_ALLOW_ORIGINS = "https://stc21.webredirect.himshang.com.np,https://admin.himshang.com.np"

- CORS_ALLOW_ORIGIN_REGEX: Regex to match dynamic origins (echoes Origin when matched)
	Defaults to allowing any subdomain of himshang.com.np and localhost.
	Example (PowerShell):
	$env:CORS_ALLOW_ORIGIN_REGEX = "^https?://([a-z0-9-]+\.)*himshang\.com\.np(:\d+)?$"

- CORS_ALLOW_CREDENTIALS: "true"/"false" (default: true)

Start server (PowerShell example):
	$env:CORS_ALLOW_ORIGIN_REGEX = "^https?://([a-z0-9-]+\.)*himshang\.com\.np(:\d+)?$"
	$env:CORS_ALLOW_CREDENTIALS = "true"
	.\.venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000

Troubleshooting CORS
--------------------
- Ensure your reverse proxy (e.g., NGINX/IIS) forwards OPTIONS requests.
- Verify preflight response:
	curl -i -X OPTIONS "https://<api-host>/extract" \
		-H "Origin: https://stc21.webredirect.himshang.com.np" \
		-H "Access-Control-Request-Method: POST" \
		-H "Access-Control-Request-Headers: content-type"
