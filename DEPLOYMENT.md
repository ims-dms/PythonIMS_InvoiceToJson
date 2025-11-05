# FastAPI Invoice Processor - Deployment & Setup Guide

## Project Overview
This project is a FastAPI-based service for extracting structured data from tax invoice documents using Gemini AI. It supports PDF/image uploads and returns strict JSON output.

---

## Requirements
- **Python Version:** 3.8 or higher (recommended: 3.13)
- **Operating System:** Linux (Ubuntu 20.04+, Debian, CentOS, etc.)
- **Dependencies:** All required Python packages are listed in `requirements.txt`.
- **External Files:**
  - `appSetting.txt` (must contain: `GEMINI_API_KEY=your_api_token_here`)

---

## Setup Instructions

### 1. Clone or Copy the Project
Transfer the project files to your Linux server (via Git, SCP, etc.).

### 2. Install Python & Tools
```sh
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

### 3. Create & Activate Virtual Environment
```sh
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```sh
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure API Key
Edit `appSetting.txt` and set your Gemini API key:
```
GEMINI_API_KEY=your_api_token_here
```

### 6. Run the Application (Development)
```sh
uvicorn api:app --host 0.0.0.0 --port 8000
```

### 7. Run the Application (Production)
```sh
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4
```

### 8. (Optional) Systemd Service for Auto-Restart
Create `/etc/systemd/system/fastapi.service`:
```
[Unit]
Description=FastAPI Service
After=network.target

[Service]
User=youruser
WorkingDirectory=/path/to/your/project
ExecStart=/path/to/your/project/.venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable and start:
```sh
sudo systemctl enable fastapi
sudo systemctl start fastapi
```

---

## API Endpoints
- `POST /extract` - Upload invoice for processing
- `GET /` - Health check

---

## Notes for DevOps
- Ensure `appSetting.txt` is present and secured.
- For HTTPS, use Nginx as a reverse proxy.
- Monitor logs for errors and usage statistics.
- Update `requirements.txt` when adding dependencies.

---

## Troubleshooting
- If you see `Missing GEMINI_API_KEY`, check `appSetting.txt`.
- For missing packages, run `pip install -r requirements.txt`.
- For import errors, verify Python version and virtual environment activation.

---

## Contact
For issues, contact the development team or check the project repository.
