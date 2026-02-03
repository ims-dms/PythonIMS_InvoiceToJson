import os
import re
import json
import base64
import logging
from datetime import datetime
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.providers.google_gla import GoogleGLAProvider
import requests
from db_connection import get_connection, create_token_tables
from token_manager import TokenManager
from retry_policy import RetryPolicy, RetryConfig
from db_logger import ApplicationLogger, log_retry_attempts
from fuzzy_matcher import match_ocr_products, format_api_response, minimize_error_message, api_error_response
from menu_cache import get_cached_menu_items, get_cache_stats, invalidate_cache

# Configure application logging (console output disabled by default to reduce noise)
ApplicationLogger.configure(log_level=logging.INFO, console=False)
logger = ApplicationLogger.get_logger(__name__)

load_dotenv()

app = FastAPI(title="Tax Invoice Processor", version="1.0.0")

origins_from_env = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
allowed_origins = [o.strip() for o in origins_from_env.split(",") if o.strip()] or [
    "http://localhost:4100",
    "http://localhost:8080",
    "http://127.0.0.1:4100",
    "http://127.0.0.1:8080",
]

allowed_origin_regex = os.getenv(
    "CORS_ALLOW_ORIGIN_REGEX",
    r"^https?://((localhost|127\.0\.0\.1)(:\\d+)?|([a-z0-9-]+\.)*himshang\.com\.np)(:\\d+)?$"
)

allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() in ("1", "true", "yes")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debug endpoint to inspect tokens in database and help diagnose "No active token" errors
@app.get("/debug/tokens")
def debug_tokens(companyID: str | None = None):
    """Return token diagnostic information.
    Optional query param 'companyID' to filter.
    Example: /debug/tokens?companyID=NT047
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        if companyID:
            cid = companyID.strip()
            cur.execute("""
                SELECT TokenID, CompanyID, CompanyName, Status, Provider, TotalTokenLimit, CreatedAt
                FROM [docUpload].TokenMaster WHERE CompanyID = ?
            """, (cid,))
        else:
            cur.execute("""
                SELECT TokenID, CompanyID, CompanyName, Status, Provider, TotalTokenLimit, CreatedAt
                FROM [docUpload].TokenMaster ORDER BY CompanyID
            """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {
            "status": "ok",
            "filter_companyID": companyID,
            "count": len(rows),
            "tokens": [
                {
                    "token_id": r[0],
                    "company_id": r[1],
                    "company_name": r[2],
                    "status": r[3],
                    "provider": r[4],
                    "total_limit": r[5],
                    "created_at": r[6].isoformat() if r[6] else None,
                } for r in rows
            ]
        }
    except Exception as e:
        logger.error(f"/debug/tokens error: {e}")
        return {"status": "error", "message": f"Failed to retrieve tokens: {e}"}

# Echo endpoint to see exactly what the server receives (query + form + headers minimal)
@app.post("/debug/echo")
async def debug_echo(
    companyID: str = Form(None),
    username: str = Form(None),
    request_file: UploadFile | None = File(None)
):
    from fastapi import Request
    # We need the raw Request object; FastAPI will inject if we declare parameter
    # But to keep existing signature small, fetch via dependency in closure
    # (Simpler: accept Request as parameter)

from fastapi import Request

@app.post("/debug/echo-full")
async def debug_echo_full(request: Request,
                          companyID: str = Form(None),
                          username: str = Form(None)):
    # Read raw body (form has been parsed already; body read may be empty for multipart)
    try:
        raw = await request.body()
    except Exception:
        raw = b''
    headers = {k: v for k, v in request.headers.items() if k.lower() in ["content-type","user-agent","content-length"]}
    logger.info(f"ECHO companyID='{companyID}', username='{username}' raw_len={len(raw)} headers={headers}")
    return {
        "received": {
            "companyID": companyID,
            "username": username,
            "raw_body_preview": raw[:200].decode(errors='ignore'),
            "raw_body_length": len(raw),
            "headers": headers
        }
    }

@app.get("/debug/company-list")
def debug_company_list(limit: int = 20):
    """List up to 'limit' company IDs from Company and matching tokens.
    Helps verify DB connection and available IDs.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        companies = []
        try:
            cur.execute("SELECT TOP (?) CompanyID FROM Company ORDER BY CompanyID", (limit,))
            companies = [r[0] for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"Company table query failed: {e}")
        tokens = {}
        try:
            cur.execute("SELECT CompanyID, Status, COUNT(*) AS cnt FROM [docUpload].TokenMaster GROUP BY CompanyID, Status")
            for cid, status, cnt in cur.fetchall():
                tokens.setdefault(cid, {}).update({status: cnt})
        except Exception as e:
            logger.warning(f"TokenMaster summary query failed: {e}")
        cur.close(); conn.close()
        return {"status":"ok","company_ids":companies,"token_summary":tokens}
    except Exception as e:
        logger.error(f"/debug/company-list error: {e}")
        return {"status":"error","message":str(e)}

# Initialize Gemini with token from database or fallback to appSetting.txt
def read_api_key_from_file(file_path='appSetting.txt'):
    """Read GEMINI_API_KEY from appSetting.txt"""
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if line.startswith('GEMINI_API_KEY='):
                    return line.split('=', 1)[1].strip()
    except Exception as e:
        raise RuntimeError(f"Failed to read API key from {file_path}: {e}")
    raise ValueError("GEMINI_API_KEY not found in appSetting.txt")

def get_gemini_model_and_api_key(company_id: str):
    """Return Gemini model and API key strictly from database.
    No fallback to appSetting.txt. Returns explicit status errors.
    """
    token_info = TokenManager.get_active_token(company_id)
    if not token_info.get('success'):
        # Bubble up structured token error
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "token_error": token_info.get('error'),
            "message": token_info.get('message'),
            "company_id": company_id,
            "statuses_present": token_info.get('statuses_present')
        })
    api_key = token_info.get('api_key')
    provider = GoogleGLAProvider(api_key=api_key)
    model = GeminiModel('gemini-2.0-flash-lite', provider=provider)
    return model, api_key, token_info

PROCESSING_PROMPT = """
CRITICAL: You will receive MULTIPLE IMAGES representing different pages of the same invoice document. You MUST process ALL images/pages and combine ALL data into a SINGLE JSON response.

Extract data from ALL PAGES of the TAX INVOICE document following these strict rules. Combine information from all provided images/pages into a single cohesive JSON output:

IMPORTANT MULTI-PAGE INSTRUCTIONS:
- If you receive multiple images, they are consecutive pages of the SAME invoice
- Product listings may span across multiple pages - extract products from EVERY page
- Aggregate all product arrays (sku, quantity, rate, etc.) from all pages into single arrays
- Header information (invoice_no, dealer_name, etc.) appears on first page - use that
- DO NOT treat each page as a separate invoice
- The final JSON must contain ALL products from ALL pages combined

1. Identify fields using common invoice terminology:
   - Order Number → "order_no"
   - Invoice Number → "invoice_no"
   - Delivery Note Number → "delivery_note"
   - Transporter Name → "transporter"
   - Vehicle Number → "vehicle_no"
   - Customer Name → "dealer_name"
   - PWS Number → "pws_no"
   - Company Name (Vendor) → "company_name"
   - Transaction Type (Mod Of payment) → "transaction_type"
   - Transaction Date → "transaction_date"
   - Due Date → "due_date"
   - Invoice Miti → "invoice_miti"
   - Invoice Date → "invoice_date"

2. For product listings:
     - There is usually a serial-number column labeled "SNO", "SN", "S.N.", or similar. Treat **every row with a serial number** as a distinct product row.
         * If the SNO values run from 1 to N (e.g., 1–30), your product arrays **MUST contain N entries**. Do not skip any SNO in the middle of the sequence.
         * If you are unsure about a row, still create a product entry with whatever fields you can read (e.g., sku, quantity, rate) so that the SNO sequence remains continuous.
     - Extract ALL SKUs from the "Description" column across ALL pages. It is very important to ensure that Description values are accurately extracted from the invoice.
         * IMPORTANT: Product description MUST be actual product names/descriptions (text that describes the product), NEVER numeric codes like HSCode.
         * IMPORTANT: If the invoice has an "Alias" column, IGNORE it completely. Do NOT map Alias values to the product description (sku field).
         * Only extract values from the explicit "Description" column, never from Alias, Item Code, or other alternative columns.
     - Extract SKU codes separately as "sku_code" across ALL pages. It is very important to ensure that SKU code values are accurately extracted from the invoice.
         * If HSCode and Alias columns are available, IGNORE them. Do NOT map these columns to sku_code.
         * Only extract actual SKU/Item codes from the explicit "SKU Code" or "Item Code" column.
     - Extract HSCode values from the "HSCode" column across ALL pages. HSCode is a 4-10 digit numeric code (like 0402, 1901, etc.).
         * CRITICAL: HSCode MUST NEVER be extracted into the "sku" field (product description).
         * CRITICAL: If you encounter a numeric code (4-10 digits, possibly with hyphens or dots), it MUST go into the "hscode" field, NOT into "sku".
         * When in doubt between Description and HSCode: text descriptions go to "sku", numeric codes go to "hscode".
     - Extract corresponding numbers from the "Quantity", "Shortage", "Breakage", "Leakage", "Batch", "SNO", "Rate", "Discount", "MRP", "VAT", "AltQty", and "Unit" columns across ALL pages.
     - Maintain array order consistency across all product-related fields, aggregating from all pages
     - CRITICAL: Always prioritize extracting from the explicitly labeled columns (Description, SKU Code, HSCode) and ignore ambiguous or aliased columns.
     - CRITICAL RULE: Do NOT concatenate or mix HSCode with product description. Keep them strictly separate.
   
   - CRITICAL RATE AND DISCOUNT EXTRACTION:
     * The "Rate" column contains the per-unit price for each product line. Read ALL digits carefully - typical rates are 3-digit to 6-digit numbers with decimals (e.g., 110.62, 221.24, 1234.56).
     * NEVER skip leading digits. If a rate looks like "110.62", extract exactly 110.62, NOT 10.62 or 0.62.
     * The "Discount" column contains per-line discount amounts. This is often a separate column AFTER the Rate column. Extract the exact discount value for EACH row.
     * If a discount value appears as blank or empty for a row, use 0.0 for that row, but always check if there IS a discount column with values.
     * Pay close attention to column boundaries - Rate and Discount are usually adjacent columns. Do NOT confuse or merge values between these columns.
     * Verify extraction: Rate values typically range from 10 to 10000; Discount values typically range from 0 to the rate value itself.
   
   - CRITICAL NUMBER FORMATTING: When extracting numeric values (quantity, rate, discount, mrp, vat, altQty):
     * The DOT (.) is ALWAYS a DECIMAL SEPARATOR, never a thousands separator
     * The COMMA (,) is ALWAYS a THOUSANDS SEPARATOR when present
     * Examples: "10.000" = 10.0 (ten with 3 decimal places), "1,234.56" = 1234.56 (one thousand two hundred thirty-four point five six), "25.000" = 25.0 (twenty-five)
     * If you see "10.000" extract it as the number 10.0, NOT 10000
     * If you see "1,000" extract it as the number 1000.0, NOT 1.0

3. Date Formatting:
   - Convert any date format to YYYY-MM-DD
   - Prefer invoice date over document creation date

4. Output Requirements:
   - Return STRICT JSON format with these EXACT field names:
     {
       "order_no": "string",
       "invoice_no": "string",
       "delivery_note": "string",
       "vehicle_no": "string",
       "transporter": "string",
       "date": "date",
       "dealer_name": "string",
       "pws_no": "string",
       "company_name": "string",
       "transaction_type": "string",
       "transaction_date": "string",
       "due_date": "string",
       "invoice_miti": "string",
       "invoice_date": "string",
             "sub_total": float,              // from totals box; may be called Gross Amount
             "discount_total": float,         // from totals box; MUST include sign if shown (e.g., -63440.25)
             "taxable_value": float,          // from totals box; sometimes called Taxable Amount/Value
             "vat_total": float,              // total VAT (e.g., VAT 13%)
             "total_amount": float,           // grand/net/total amount to pay
       "sku": ["string"],
       "sku_code": ["string"],
       "quantity": [int],
       "shortage": [int],
       "breakage": [int],
       "leakage": [int],
       "batch": ["string"],
       "sno": ["string"],
       "rate": [float],
       "discount": [float],
       "mrp": [float],
       "vat": [float],
       "hscode": ["string"],
       "altQty": [int],
       "unit": ["string"]
     }
     - Always extract totals from the totals panel when present and prefer these over computations.
     - Return empty strings/arrays for missing data; however, totals should be present whenever the invoice has them.
     - Preserve negative signs shown for discount; do not convert to positive.
   - ABSOLUTELY NO ADDITIONAL TEXT OR MARKDOWN

IMPORTANT VERIFICATION - Before finalizing your response:
   - Double-check the "rate" array: Each rate value should include ALL visible digits. Rates like 110.62 should NOT become 10.62.
   - Double-check the "discount" array: If a Discount column exists in the invoice, extract the per-line discount values. Do NOT return all zeros if discounts are clearly visible.
   - Cross-verify: The "Amount" column (if present) should approximately equal Rate × Quantity - Discount for each row.

FINAL REMINDER: If multiple images were provided, ensure you have extracted products from EVERY SINGLE PAGE. Your product arrays (sku, quantity, rate, etc.) should contain entries from ALL pages combined, not just the first page.
"""

def convert_pdf_bytes_to_pngs(file_bytes: bytes):
    """Convert all pages of a PDF (bytes) to a list of PNG bytes.
    Tries poppler/pdf2image first; if that fails, falls back to PyMuPDF (fitz) if available.
    Raises a RuntimeError with an explanatory message if both methods fail.
    Returns: list of (png_bytes, media_type)
    """
    try:
        # Prefer pdf2image/poppler when available
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(file_bytes)
        out = []
        for img in images:
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='PNG')
            out.append((img_byte_arr.getvalue(), 'image/png'))
        return out
    except Exception as e_pdf:
        # Attempt a graceful fallback using PyMuPDF (fitz)
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=file_bytes, filetype='pdf')
            out = []
            for page_no in range(doc.page_count):
                page = doc.load_page(page_no)
                # render at 2x for better OCR quality
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes('png')
                out.append((img_bytes, 'image/png'))
            return out
        except Exception as e_fitz:
            # Combined error to help debugging and user instructions
            msg = (
                f"Failed to convert PDF to images. pdf2image error: {e_pdf}; "
                f"PyMuPDF fallback error: {e_fitz}.\n"
                "Ensure poppler is installed and in PATH (for pdf2image), or install PyMuPDF: `pip install PyMuPDF`."
            )
            raise RuntimeError(msg)

def validate_response_structure(data: dict) -> bool:
    required_fields = [
        'order_no', 'invoice_no', 'delivery_note', 'vehicle_no',
        'transporter', 'date', 'dealer_name', 'pws_no', 'company_name',
        'transaction_type', 'transaction_date', 'due_date', 'invoice_miti', 'invoice_date',
        'sku', 'sku_code', 'quantity', 'shortage', 'breakage', 'leakage',
        'hscode', 'altQty', 'unit', 'discount', 'sno'
    ]
    return all(field in data for field in required_fields)

def normalize_arrays(data: dict) -> dict:
    # Include 'sku_code' to keep row alignment stable across pages
    # Also include 'rate' so that per-line arrays remain aligned even if a page is missing values
    array_fields = ['sku', 'sku_code', 'quantity', 'shortage', 'breakage', 'leakage', 'hscode', 'altQty', 'unit', 'discount', 'rate', 'sno']
    max_length = max(len(data.get(field, [])) for field in array_fields)
    
    for field in array_fields:
        if len(data.get(field, [])) != max_length:
            if field in ['quantity', 'shortage', 'breakage', 'leakage', 'altQty', 'discount', 'rate']:
                data[field] = data.get(field, []) + [0]*(max_length - len(data.get(field, [])))
            else:
                data[field] = data.get(field, []) + [""]*(max_length - len(data.get(field, [])))
    
    for field in ['transaction_type', 'transaction_date', 'due_date', 'invoice_miti', 'invoice_date']:
        if field not in data:
            data[field] = ""
    
    return data

@app.post("/extract")
async def process_invoice(
    request: Request,
    file: UploadFile = File(None),
    companyID: str = Form(...),
    username: str = Form(...),
    branch: str = Form(None),
    Division: str = Form(None),
    licenceID: str = Form(None),
    connection_params: str = Form(None),  # New parameter for connection parameters as JSON string
    extractFromLink: int = Form(0),
    pdf_url: str = Form(None)
):
    """
    Process invoice with token management and retry logic
    """
    # Log raw request meta for debugging companyID mismatch issues
    try:
        headers_subset = {k: v for k, v in request.headers.items() if k.lower() in ["content-type","user-agent","content-length"]}
        logger.info(f"RAW REQUEST META headers={headers_subset} client={request.client}")
    except Exception as e:
        logger.debug(f"Failed to capture raw headers: {e}")

    # Read raw form in a robust, case-insensitive way to capture Division/branch regardless of client casing
    try:
        raw_form = await request.form()
        # Normalize keys to lowercase for lookup
        form_map = {k.lower(): v for k, v in raw_form.items()}
    except Exception:
        form_map = {}

    # Clean up form inputs to remove any leading/trailing whitespace
    companyID = (companyID.strip() if companyID else companyID) or (form_map.get('companyid') or form_map.get('companyid'.lower()))
    username = username.strip() if username else (form_map.get('username') or form_map.get('requestedby'))
    branch = branch.strip() if branch else None

    # Try multiple possible keys for division/branch in incoming form (case-insensitive)
    division_candidates = [
        form_map.get('division'), form_map.get('divisionname'), form_map.get('branch'),
        form_map.get('dept'), form_map.get('department')
    ]
    # prefer explicit Division param first, then candidates, then branch param
    Division = (Division.strip() if Division else None) or next((c for c in division_candidates if c), None)

    # Prefer explicit Division field if provided, otherwise fall back to branch
    effective_branch = (Division or branch or 'Default')

    logger.info(f"RECEIVED REQUEST: companyID='{companyID}' (len={len(companyID) if companyID else 0}), username='{username}', branch='{effective_branch}'")
    
    if not companyID or not username:
        return format_api_response(
            message="Please provide both companyID and username.",
            status="error"
        )
    
    # Initialize token info
    token_info = None
    token_id = None
    retry_policy = None
    
    try:
        # Get active token (this will also validate token exists and is active)
        logger.info(f"LOOKING UP TOKEN for companyID='{companyID}'")
        token_result = TokenManager.get_active_token(companyID)
        logger.info(f"TOKEN LOOKUP RESULT: {token_result}")
        if not token_result.get('success'):
            logger.warning(f"TOKEN LOOKUP FAILED for company {companyID}: {token_result.get('message')}")
            return format_api_response(
                message=token_result.get('message'),
                status="error"
            )
        
        token_info = token_result
        token_id = token_info.get('token_id')
        logger.info(f"Token {token_id} selected for company {companyID}")
    
    except Exception as e:
        logger.error(f"Token retrieval error: {e}")
        return format_api_response(
            message="Failed to retrieve API token. Please contact support.",
            status="error"
        )
    
    try:
        # Initialize retry policy
        retry_config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=30.0,
            backoff_multiplier=2.0,
            jitter=True
        )
        retry_policy = RetryPolicy(retry_config)
        
        # Get file content
        if extractFromLink == 1:
            if not pdf_url:
                return format_api_response(
                    message="pdf_url is required when extractFromLink=1",
                    status="error"
                )
            try:
                response = requests.get(pdf_url)
                response.raise_for_status()
                file_content = response.content
                file_name = pdf_url.split('/')[-1].split('?')[0]
                content_type = "application/pdf"
            except requests.RequestException as e:
                logger.error(f"Failed to download PDF from URL: {e}")
                return format_api_response(
                    message="Failed to download PDF from URL",
                    data={"actual_error": str(e)},
                    status="error"
                )
        else:
            if not file:
                return format_api_response(
                    message="file is required when extractFromLink=0",
                    status="error"
                )
            file_content = await file.read()
            file_name = file.filename
            content_type = file.content_type
        
        # Validate file content
        if not file_content:
            return format_api_response(
                message="File is empty",
                status="error"
            )
        
        # Convert PDF to images
        try:
            binary_contents = []
            if content_type == "application/pdf":
                try:
                    images = convert_pdf_bytes_to_pngs(file_content)
                    logger.info(f"Converted {len(images)} pages from PDF")
                except Exception as e:
                    logger.error(f"PDF conversion failed: {e}")
                    return format_api_response(
                        message="Failed to convert PDF",
                        data={"actual_error": str(e)},
                        status="error"
                    )
                
                first_img_bytes, first_media = images[0]
                for img_bytes, media in images:
                    binary_contents.append(BinaryContent(img_bytes, media_type=media))
                logger.info(f"Created {len(binary_contents)} binary content objects for Gemini processing")
            else:
                media_type = content_type or 'application/octet-stream'
                binary_contents.append(BinaryContent(file_content, media_type=media_type))
            
            # Build agent inputs
            agent_inputs = [PROCESSING_PROMPT] + binary_contents
            logger.info(f"Agent inputs prepared: 1 prompt + {len(binary_contents)} images = {len(agent_inputs)} total inputs")
            
            # Get Gemini model with retry logic
            async def process_with_gemini():
                model, api_key, _ = get_gemini_model_and_api_key(companyID)
                gemini_agent = Agent(model)
                logger.info(f"Sending {len(binary_contents)} images to Gemini for processing")
                result = await gemini_agent.run(agent_inputs)
                return result
            
            # Execute with retry policy
            logger.info("Starting Gemini processing with retry policy...")
            result = await retry_policy.execute_with_retry(process_with_gemini)
            
            # Get usage information
            usage = result.usage()
            usage_info = f"Gemini processing complete. Usage: {usage}"
            logger.info(usage_info)
            
            # Extract usage details and log to database
            usage_details = TokenManager.extract_usage_from_log(usage_info)
            if usage_details and token_id:
                log_result = TokenManager.log_token_usage(
                    token_id=token_id,
                    usage_info=usage_details,
                    branch=effective_branch,
                    requested_by=username
                )
                if not log_result.get('success'):
                    logger.warning(f"Failed to log token usage: {log_result.get('message')}")
            
            # Log retry attempts if any occurred
            if retry_policy.retry_count > 0:
                log_retry_attempts(
                    retry_policy.get_retry_log(),
                    token_id=token_id,
                    company_id=companyID
                )
                logger.info(f"Retry attempts logged: {retry_policy.retry_count}")
            
            # Extract and process response
            raw_response = result.output if hasattr(result, 'output') else str(result)

            try:
                # Robust JSON extraction for multi-page responses (balanced brace matching)
                def extract_json_object(text: str):
                    # Prefer code block start if present
                    md = re.search(r"```(?:json)?\s*", text)
                    start = md.end() if md else text.find('{')
                    if start == -1:
                        return None
                    brace = 0
                    in_str = False
                    esc = False
                    for i in range(start, len(text)):
                        ch = text[i]
                        if in_str:
                            if esc:
                                esc = False
                            elif ch == '\\':
                                esc = True
                            elif ch == '"':
                                in_str = False
                            continue
                        else:
                            if ch == '"':
                                in_str = True
                                continue
                            if ch == '{':
                                brace += 1
                            elif ch == '}':
                                brace -= 1
                                if brace == 0:
                                    return text[start:i+1]
                    return None

                def repair_json(js: str):
                    # Quote unquoted keys
                    s = re.sub(r'([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', js)
                    # Remove trailing commas
                    s = re.sub(r',\s*([}\]])', r'\1', s)
                    # Iteratively fix comma/colon errors based on parser position
                    for _ in range(20):
                        try:
                            return json.loads(s)
                        except json.JSONDecodeError as e:
                            pos = getattr(e, 'pos', None)
                            msg = e.msg or ''
                            if pos is None or pos < 0 or pos > len(s):
                                break
                            if "Expecting ',' delimiter" in msg:
                                s = s[:pos] + ',' + s[pos:]
                                s = re.sub(r',\s*([}\]])', r'\1', s)
                                continue
                            if "Expecting ':' delimiter" in msg:
                                s = s[:pos] + ':' + s[pos:]
                                continue
                            if "property name enclosed in double quotes" in msg:
                                seg_start = max(0, pos - 50)
                                seg_end = min(len(s), pos + 50)
                                seg = s[seg_start:seg_end]
                                seg = re.sub(r'([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', seg)
                                s = s[:seg_start] + seg + s[seg_end:]
                                continue
                            break
                    return s

                json_str = extract_json_object(raw_response)
                if not json_str:
                    raise ValueError("No JSON found in Gemini response")

                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as e1:
                    # Attempt more aggressive repairs for malformed JSON coming from model
                    def aggressive_repair(s: str):
                        # Strip non-printable/control characters
                        s = ''.join(ch for ch in s if ch.isprintable())
                        # Replace Python-style single quotes with double quotes where safe
                        s = re.sub(r"(?<=[:\[,\{\s])'([^']*)'(?=[,\]\}\s])", r'"\1"', s)
                        # Quote unquoted keys (again)
                        s = re.sub(r'([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', s)
                        # Replace Python None/True/False with JSON null/true/false
                        s = s.replace('None', 'null').replace('True', 'true').replace('False', 'false')
                        # Remove thousands separators from numbers (e.g., 8,841.35 -> 8841.35)
                        # Target common positions first
                        s = re.sub(r':\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', lambda m: ':' + m.group(1).replace(',', ''), s)
                        s = re.sub(r'\[\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', lambda m: '[' + m.group(1).replace(',', ''), s)
                        s = re.sub(r',\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', lambda m: ',' + m.group(1).replace(',', ''), s)
                        # Global fallback: remove commas in numeric tokens not inside quotes
                        s = re.sub(r'(?<!\")((?:-)?\d{1,3}(?:,\d{3})+(?:\.\d+)?)(?!\")',
                                   lambda m: m.group(1).replace(',', ''), s)
                        # Remove trailing commas before } or ]
                        s = re.sub(r',\s*([}\]])', r'\1', s)
                        # If multiple top-level braces, take the largest balanced object
                        first = s.find('{')
                        last = s.rfind('}')
                        if first != -1 and last != -1 and last > first:
                            s = s[first:last+1]
                        return s

                    try:
                        repaired1 = repair_json(json_str)
                        repaired2 = aggressive_repair(json_str)
                        parsed = None
                        # Try repaired1 (existing algorithm) first
                        if isinstance(repaired1, (dict, list)):
                            parsed = repaired1
                        else:
                            try:
                                parsed = json.loads(repaired1)
                            except Exception:
                                parsed = None

                        # If still not parsed, try aggressive repaired2
                        if parsed is None:
                            try:
                                parsed = json.loads(repaired2)
                            except Exception:
                                parsed = None

                        if parsed is None:
                            # Parsing failed; raise a detailed error for diagnostics
                            preview_raw = (raw_response[:2000] + '...') if len(raw_response) > 2000 else raw_response
                            preview_json = (json_str[:1000] + '...') if len(json_str) > 1000 else json_str
                            raise ValueError(f"JSON parse failed after repairs: original_error={e1}; json_preview={preview_json}; raw_preview={preview_raw}")

                        data = parsed
                    except Exception as e2:
                        # Bubble up a clear error including original decode issue and previews
                        preview_raw = (raw_response[:2000] + '...') if len(raw_response) > 2000 else raw_response
                        preview_json = (json_str[:1000] + '...') if len(json_str) > 1000 else json_str
                        raise ValueError(f"JSON parsing error: original={e1}; repair_error={e2}; json_preview={preview_json}; raw_preview={preview_raw}")
                
                # Normalize and process data
                def normalize_key(k):
                    return k.replace(" ", "").replace("_", "").lower()
                
                normalized_data = {}
                for key, value in data.items():
                    normalized_data[normalize_key(key)] = value
                
                if not validate_response_structure(data):
                    raise ValueError("Response missing required fields")
                
                data = normalize_arrays(data)
                data['sku'] = data.get('sku', [])
                data['brands'] = [sku.split()[0] if sku else "" for sku in data.get('sku', [])]

                # Extract invoice-level totals if present in model output
                def pick_number(*candidates):
                    import re
                    for c in candidates:
                        val = normalized_data.get(c)
                        if val is not None:
                            # Some models return strings; coerce safely
                            try:
                                if isinstance(val, (int, float)):
                                    return float(val)
                                if isinstance(val, str):
                                    # robust numeric parse: keep optional leading minus, digits and dot
                                    m = re.search(r"-?\d[\d,]*\.?\d*", val)
                                    if m:
                                        return float(m.group(0).replace(',', ''))
                                # If array provided accidentally, pick first numeric
                                if isinstance(val, list) and val:
                                    for item in val:
                                        try:
                                            m = re.search(r"-?\d[\d,]*\.?\d*", str(item))
                                            if m:
                                                return float(m.group(0).replace(',', ''))
                                        except Exception:
                                            continue
                            except Exception:
                                continue
                    return None

                # Helper to safely parse individual numeric values from strings and mixed inputs
                def parse_number_safe(value):
                    import re
                    try:
                        if value is None:
                            return 0
                        if isinstance(value, (int, float)):
                            result = float(value)
                            # Screen OCR correction: if number is divisible by 1000 (like 10000, 25000)
                            # it may be misinterpreted "10.000" or "25.000" from screen photos
                            if result >= 1000 and result % 1000 == 0 and result <= 100000:
                                candidate = result / 1000.0
                                if candidate >= 1 and candidate <= 999:  # Reasonable quantity/rate range
                                    return candidate
                            return result
                        s = str(value)
                        # OCR normalization: fix ambiguous leading characters commonly mistaken for digits
                        # Example: 'I10.62' or 'l10.62' or '|10.62' should be treated as '110.62'
                        s_norm = s
                        # If a token starts with I/l/| followed by digits, convert the leading char to '1'
                        s_norm = re.sub(r"\b[Il\|](?=\d)", "1", s_norm)
                        # Sometimes 'O' may be used instead of '0' adjacent to digits
                        s_norm = re.sub(r"(?<=\d)[Oo](?=\d)", "0", s_norm)

                        # Extract first well-formed number token; keep decimals, strip thousands commas
                        m = re.search(r"-?\d[\d,]*\.?\d*", s_norm)
                        candidate_result = None
                        if m:
                            token = m.group(0)
                            try:
                                candidate_result = float(token.replace(',', ''))
                            except Exception:
                                candidate_result = None

                        # Secondary attempt: allow optional leading I/l/| inside the token and replace with '1'
                        if candidate_result is None or (candidate_result < 20 and re.search(r"\b[Il\|]\d", s)):
                            m2 = re.search(r"[Il\|]?\d[\d,]*\.?\d*", s)
                            if m2:
                                token2 = m2.group(0).replace('I', '1').replace('l', '1').replace('|', '1')
                                try:
                                    candidate2 = float(token2.replace(',', ''))
                                    # Prefer candidate2 if it looks more reasonable for rate-like values
                                    if candidate_result is None or candidate2 >= 20 > candidate_result:
                                        candidate_result = candidate2
                                except Exception:
                                    pass

                        if candidate_result is not None:
                            # Apply the screen OCR thousands-separator correction if needed
                            if candidate_result >= 1000 and candidate_result % 1000 == 0 and candidate_result <= 100000:
                                candidate = candidate_result / 1000.0
                                if candidate >= 1 and candidate <= 999:
                                    return candidate
                            return candidate_result
                    except Exception:
                        pass
                    return 0

                sub_total = pick_number('subtotal', 'sub_total', 'totalbeforediscount', 'grossamount')
                # Avoid generic 'discount' which may refer to per-line column
                discount_total = pick_number('discounttotal', 'totaldiscount', 'discountamount', 'discount_amount')
                taxable_value = pick_number('taxablevalue', 'taxable_value', 'taxableamount')
                vat_total = pick_number('vat_total', 'tax_total', 'vat13', 'vatvalue')
                grand_total = pick_number('totalamount', 'grandtotal', 'netamount', 'total_amount')

                # Attach prioritized totals to the response if found (use distinct keys)
                if sub_total is not None:
                    data['sub_total'] = sub_total
                if discount_total is not None:
                    data['discount_total'] = discount_total
                if taxable_value is not None:
                    data['taxable_value'] = taxable_value
                if vat_total is not None:
                    data['vat_total'] = vat_total
                if grand_total is not None:
                    data['total_amount'] = grand_total
                
                # Process products
                products = []
                sku_list = data.get('sku', [])
                sku_code_list = data.get('sku_code', [])
                # Prefer original model outputs (normalized_data) to preserve formatting like "10.000"
                quantity_list = normalized_data.get('quantity') or data.get('quantity', [])
                shortage_list = normalized_data.get('shortage') or data.get('shortage', [])
                breakage_list = normalized_data.get('breakage') or data.get('breakage', [])
                leakage_list = normalized_data.get('leakage') or data.get('leakage', [])
                batch_list = normalized_data.get('batch') or []
                sno_list = data.get('sno', [])
                rate_list = normalized_data.get('rate') or data.get('rate', []) or []
                # Ensure we only treat per-line discounts as lists; scalar invoice discounts are handled separately
                discount_list_raw = (
                    normalized_data.get('discount')
                    or normalized_data.get('discountamount')
                    or normalized_data.get('discount_value')
                    or data.get('discount')
                    or []
                )
                discount_list = discount_list_raw if isinstance(discount_list_raw, list) else []
                mrp_list = normalized_data.get('mrp') or normalized_data.get('mrpvalue') or []
                vat_list = (normalized_data.get('vat') or normalized_data.get('vatvalue') or []) if isinstance((normalized_data.get('vat') or normalized_data.get('vatvalue') or []), list) else []
                hscode_list = normalized_data.get('hscode') or normalized_data.get('hs_code') or []
                altqty_list = normalized_data.get('altqty') or normalized_data.get('altquantity') or []
                unit_list = normalized_data.get('unit') or normalized_data.get('unitofmeasure') or normalized_data.get('uom') or []

                # Disambiguate HSCode vs ItemCode (sku_code): do not let HSCode leak into sku_code
                def _norm_str(v):
                    try:
                        return str(v).strip()
                    except Exception:
                        return ""

                def _is_hscode_like(v: str) -> bool:
                    s = _norm_str(v)
                    # HS codes are typically 4-8+ digits, with only digits (sometimes with dots)
                    return bool(re.fullmatch(r"\d{4,10}(?:[.\-]\d{1,4})?", s))

                try:
                    # Step 1: If both lists exist and are effectively identical, blank out sku_code_list
                    if hscode_list and sku_code_list:
                        total = max(len(hscode_list), len(sku_code_list))
                        same = 0
                        for i in range(total):
                            hs = _norm_str(hscode_list[i]) if i < len(hscode_list) else ""
                            sc = _norm_str(sku_code_list[i]) if i < len(sku_code_list) else ""
                            if hs and sc and hs == sc:
                                same += 1
                        if total and same / total >= 0.7:
                            sku_code_list = []
                    # Step 2: If HSCode not present but sku_code looks numeric HS codes, move them to hscode
                    elif (not hscode_list) and sku_code_list:
                        hslikes = sum(1 for v in sku_code_list if _is_hscode_like(v))
                        if hslikes and hslikes / len(sku_code_list) >= 0.7:
                            hscode_list = sku_code_list
                            sku_code_list = []
                    
                    # Step 3: Move HSCode-like values from sku to hscode when sku incorrectly contains HS codes
                    # This fixes the issue where OCR extracts "100830" into the description field
                    max_items = max(len(sku_list), len(sku_code_list), len(hscode_list))
                    for i in range(max_items):
                        sku_val = _norm_str(sku_list[i]) if i < len(sku_list) else ""
                        sku_code_val = _norm_str(sku_code_list[i]) if i < len(sku_code_list) else ""
                        hs_val = _norm_str(hscode_list[i]) if i < len(hscode_list) else ""
                        
                        # If sku contains an HS code (purely numeric), move it to hscode
                        if sku_val and _is_hscode_like(sku_val):
                            # Move to hscode if hscode is empty
                            if not hs_val:
                                if i < len(hscode_list):
                                    hscode_list[i] = sku_val
                                else:
                                    hscode_list.append(sku_val)
                            # Clear the sku
                            if i < len(sku_list):
                                sku_list[i] = ""
                            sku_val = ""  # Update for next check
                        
                        # If sku is now empty but sku_code exists and is not an HS code, move sku_code to sku
                        # This handles cases like "1212-MM" which are product codes, not HS codes
                        if not sku_val and sku_code_val and not _is_hscode_like(sku_code_val):
                            # Move sku_code to sku
                            if i < len(sku_list):
                                sku_list[i] = sku_code_val
                            else:
                                sku_list.append(sku_code_val)
                            # Clear the sku_code
                            if i < len(sku_code_list):
                                sku_code_list[i] = ""
                except Exception:
                    # Non-fatal; continue with original lists
                    pass

                # Sanitize numeric lists early to avoid any downstream mis-parsing
                quantity_list = [parse_number_safe(x) for x in quantity_list]
                shortage_list = [parse_number_safe(x) for x in shortage_list]
                breakage_list = [parse_number_safe(x) for x in breakage_list]
                leakage_list = [parse_number_safe(x) for x in leakage_list]
                rate_list = [parse_number_safe(x) for x in rate_list]
                discount_list = [parse_number_safe(x) for x in discount_list]
                mrp_list = [parse_number_safe(x) for x in mrp_list]
                vat_list = [parse_number_safe(x) for x in vat_list]
                altqty_list = [parse_number_safe(x) for x in altqty_list]

                # Heuristic correction: if a rate looks unrealistically low and per-line discount exceeds it,
                # it likely lost a leading '1' during OCR (e.g., 110.62 -> 10.62). Add 100 in such cases.
                try:
                    for i in range(min(len(rate_list), len(discount_list))):
                        r = float(rate_list[i] or 0)
                        d = float(discount_list[i] or 0)
                        if r > 0 and r < 20 and d > r:
                            rate_list[i] = r + 100.0
                except Exception:
                    pass
                
                # Determine the number of product rows based on actual line-item fields
                # Avoid using SNO length alone, because the model may output extra serial
                # numbers without corresponding description/amount data, which would
                # otherwise create empty placeholder products.
                max_len = max(
                    len(sku_list), len(sku_code_list), len(quantity_list), len(shortage_list),
                    len(breakage_list), len(leakage_list), len(batch_list),
                    len(rate_list), len(discount_list),
                    len(mrp_list), len(vat_list), len(hscode_list),
                    len(altqty_list), len(unit_list)
                )
                
                for i in range(max_len):
                    product = {
                        "sku": sku_list[i] if i < len(sku_list) else "",
                        "sku_code": sku_code_list[i] if i < len(sku_code_list) else "",
                        # Already sanitized lists
                        "quantity": quantity_list[i] if i < len(quantity_list) else 0,
                        "shortage": shortage_list[i] if i < len(shortage_list) else 0,
                        "breakage": breakage_list[i] if i < len(breakage_list) else 0,
                        "leakage": leakage_list[i] if i < len(leakage_list) else 0,
                        "batch": batch_list[i] if i < len(batch_list) else "",
                        "sno": sno_list[i] if i < len(sno_list) else "",
                        "rate": rate_list[i] if i < len(rate_list) else 0,
                        "discount": discount_list[i] if i < len(discount_list) else 0,
                        "mrp": mrp_list[i] if i < len(mrp_list) else 0,
                        "vat": vat_list[i] if i < len(vat_list) else 0,
                        "hscode": hscode_list[i] if i < len(hscode_list) else "",
                        "altQty": altqty_list[i] if i < len(altqty_list) else 0,
                        "unit": unit_list[i] if i < len(unit_list) else ""
                    }
                    # Do not alter 'sku' even if it looks like a code.
                    # The user requires whatever appears in the Description column
                    # to remain in 'sku' exactly as printed.
                    products.append(product)

                # Drop spurious rows created by misaligned numeric lists (e.g., extra SNO values
                # without any description/code or meaningful quantities).
                # Keep only rows that have at least a product description or a sku_code.
                products = [
                    p for p in products
                    if (str(p.get('sku') or '').strip() or str(p.get('sku_code') or '').strip())
                ]
                
                logger.info(f"Extracted {len(products)} products after filtering (sent {len(binary_contents)} pages to Gemini)")

                # Debug log suspicious numeric formats to help diagnose issues in production
                try:
                    if products:
                        sample = products[0]
                        qty_raw = data.get('quantity',[None])[0] if isinstance(data.get('quantity'), list) and data.get('quantity') else None
                        rate_raw = data.get('rate',[None])[0] if isinstance(data.get('rate'), list) and data.get('rate') else None
                        discount_raw = data.get('discount',[None])[0] if isinstance(data.get('discount'), list) and data.get('discount') else None
                        logger.debug(
                            f"Numeric parse sample -> qty_raw='{qty_raw}', rate_raw='{rate_raw}', discount_raw='{discount_raw}', "
                            f"qty_parsed={sample.get('quantity')}, rate_parsed={sample.get('rate')}, discount_parsed={sample.get('discount')}"
                        )
                except Exception:
                    pass

                # Compute fallback totals from products if OCR didn't provide
                try:
                    computed_sub_total = sum(float(rate_list[i] if i < len(rate_list) else 0) * float(quantity_list[i] if i < len(quantity_list) else 0) for i in range(max_len))
                except Exception:
                    computed_sub_total = None

                try:
                    computed_discount_total = None
                    if isinstance(discount_list, list) and len(discount_list) == max_len:
                        computed_discount_total = sum(float(discount_list[i] or 0) for i in range(max_len))
                except Exception:
                    computed_discount_total = None

                try:
                    computed_taxable_value = None
                    if computed_sub_total is not None:
                        if data.get('discount_total') is not None:
                            computed_taxable_value = computed_sub_total - float(data['discount_total'])
                        elif computed_discount_total is not None:
                            computed_taxable_value = computed_sub_total - computed_discount_total
                        else:
                            computed_taxable_value = computed_sub_total
                except Exception:
                    computed_taxable_value = None

                # If totals are missing, fill with computed values where safe
                if data.get('sub_total') is None and computed_sub_total is not None:
                    data['sub_total'] = round(computed_sub_total, 2)
                # Prefer OCR totals; if missing, compute from per-line discounts
                if data.get('discount_total') is None and computed_discount_total is not None:
                    data['discount_total'] = round(computed_discount_total, 2)
                if data.get('taxable_value') is None and computed_taxable_value is not None:
                    data['taxable_value'] = round(computed_taxable_value, 2)

                # Infer VAT total from grand total and taxable value if available
                if data.get('vat_total') is None and data.get('total_amount') is not None and data.get('taxable_value') is not None:
                    try:
                        data['vat_total'] = round(float(data['total_amount']) - float(data['taxable_value']), 2)
                    except Exception:
                        pass

                # Final consistency attempt: if sub_total and total_amount plus vat_total known, derive discount
                if data.get('discount_total') in (None, 0) and data.get('sub_total') is not None:
                    try:
                        if data.get('taxable_value') is not None and float(data['taxable_value']) <= float(data['sub_total']) - 0.01:
                            data['discount_total'] = round(float(data['sub_total']) - float(data['taxable_value']), 2)
                        elif data.get('total_amount') is not None and data.get('vat_total') is not None:
                            # discount = sub_total + vat_total - total_amount
                            data['discount_total'] = round(float(data['sub_total']) + float(data['vat_total']) - float(data['total_amount']), 2)
                    except Exception:
                        pass
                
                logger.debug(f"Raw SKU data from Gemini response: {data.get('sku', [])}")
                
                # Fetch menu items using intelligent caching
                import json as json_lib
                
                def fetch_menu_items_from_db():
                    if connection_params:
                        try:
                            conn_params_dict = json_lib.loads(connection_params)
                        except Exception as e:
                            raise ValueError(f"Invalid connection_params JSON: {str(e)}")
                        conn = get_connection(conn_params_dict)
                    else:
                        conn = get_connection()
                    
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT m.desca,
                               m.mcode,
                               m.menucode,
                               a.BASEUOM as baseunit,
                               a.CONFACTOR,
                               a.altunit,
                               m.VAT as vat
                        FROM menuitem m
                        LEFT JOIN MULTIALTUNIT a ON m.mcode = a.mcode
                        WHERE m.type = 'A' and m.isactive = 1
                    """)
                    items = cursor.fetchall()
                    cursor.close()
                    conn.close()
                    return items
                
                logger.info("Retrieving menu items for fuzzy matching...")
                menu_items = get_cached_menu_items(fetch_menu_items_from_db)
                cache_stats = get_cache_stats()
                logger.info(f"Menu items retrieved. Cache status: {cache_stats['status']}, "
                           f"Count: {cache_stats['item_count']}, Age: {cache_stats['age_seconds']}s")
                
                # Get database connection for OCRMappedData lookup
                if connection_params:
                    try:
                        conn_params_dict = json_lib.loads(connection_params)
                    except Exception as e:
                        return format_api_response(
                            message="Invalid connection parameters",
                            data={"actual_error": str(e)},
                            status="error"
                        )
                    db_conn = get_connection(conn_params_dict)
                else:
                    db_conn = get_connection()
                
                # Apply fuzzy matching to products
                logger.info(f"Starting fuzzy matching for {len(products)} products...")
                supplier_name = (data.get('company_name', '') or '').strip()
                logger.info(f"Supplier name extracted from invoice: '{supplier_name}'")
                logger.info(f"Database connection available: {db_conn is not None}")
                
                products = match_ocr_products(
                    ocr_products=products,
                    menu_items=menu_items,
                    top_k=3,
                    score_cutoff=60.0,
                    connection=db_conn,
                    supplier_name=supplier_name
                )
                logger.info("Fuzzy matching completed successfully")
                
                # Derive isVAT strictly from menuitem.VAT (0/1) using best_match mcode
                try:
                    mcode_to_vat = {}
                    for it in menu_items:
                        if it and len(it) > 6:
                            mcode_to_vat[it[1]] = it[6]
                    for p in products:
                        bm = p.get('best_match') or {}
                        mcode = bm.get('mcode')
                        val = 0
                        if mcode and mcode in mcode_to_vat:
                            try:
                                val = 1 if str(int(mcode_to_vat[mcode])) == '1' else 0
                            except Exception:
                                val = 1 if str(mcode_to_vat[mcode]).strip() in ('1','Y','y','true','True') else 0
                        p['isVAT'] = val
                except Exception as _e:
                    logger.warning(f"Failed to compute isVAT from menu items: {_e}")

                db_conn.close()
                
                # Clean up response data: remove array fields only, preserve scalar totals
                for key in ['sku', 'quantity', 'shortage', 'breakage', 'leakage', 'batch', 'sno', 'rate', 'discount', 'mrp', 'vat', 'brands']:
                    if isinstance(data.get(key), list):
                        data.pop(key, None)
                
                data['products'] = products

                # Do not perform a post-pass that clears or alters SKU.
                
                for key in ['sku_code', 'hscode', 'altQty', 'unit', 'full_sku_names']:
                    data.pop(key, None)
                
                return format_api_response(
                    data=data,
                    message="Invoice processed successfully",
                    status="ok"
                )
            
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Processing error: {str(e)}")
                return format_api_response(
                    message="Failed to process invoice",
                    data={"actual_error": str(e)},
                    status="error"
                )
        
        except Exception as e:
            # Check if error is retryable
            if retry_policy and not retry_policy.is_retryable_error(e):
                logger.error(f"Non-retryable error: {str(e)}")
                return format_api_response(
                    message=minimize_error_message(str(e)),
                    data={"actual_error": str(e)},
                    status="error"
                )
            
            # Log retry attempts if any
            if retry_policy and retry_policy.retry_count > 0:
                log_retry_attempts(
                    retry_policy.get_retry_log(),
                    token_id=token_id,
                    company_id=companyID
                )
            
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            error_detail = str(e)
            user_message = minimize_error_message(error_detail)
            
            return format_api_response(
                message=user_message,
                data={"actual_error": error_detail},
                status="error"
            )
    
    except Exception as e:
        # Insert failure record in tblOCRTokenDetails
        from datetime import date, datetime as dt
        current_date = date.today()
        current_time = dt.now().time()
        
        try:
            conn = get_connection()
            cursor = conn.cursor()
            create_table_sql = """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='tblOCRTokenDetails' AND xtype='U')
            CREATE TABLE tblOCRTokenDetails (
                Id INT IDENTITY(1,1) PRIMARY KEY,
                CompanyId VARCHAR(255),
                Username VARCHAR(255),
                LicenceID VARCHAR(255),
                Requests INT,
                RequestTokens INT,
                ResponseTokens INT,
                TotalTokens INT,
                Date DATE,
                Time TIME,
                Status VARCHAR(50),
                Remarks VARCHAR(MAX)
            )
            """
            cursor.execute(create_table_sql)
            insert_sql = """
            INSERT INTO tblOCRTokenDetails (CompanyId, Username, LicenceID, Requests, RequestTokens, ResponseTokens, TotalTokens, Date, Time, Status, Remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(insert_sql, (
                companyID,
                username,
                licenceID,
                0,
                0,
                0,
                0,
                current_date,
                current_time,
                "Failure",
                str(e)
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as ex:
            logger.error(f"Failed to log failure in tblOCRTokenDetails: {ex}")
        
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        error_detail = str(e)
        user_message = minimize_error_message(error_detail)
        
        return format_api_response(
            message=user_message,
            data={"actual_error": error_detail},
            status="error"
        )

@app.get("/")
async def health_check():
    return {
        "status": "active",
        "version": app.version,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/cache/status")
async def cache_status():
    """Get current menu item cache statistics."""
    stats = get_cache_stats()
    return {
        "cache": stats,
        "message": "Cache is healthy" if stats['status'] == 'valid' else "Cache needs refresh"
    }

@app.post("/cache/invalidate")
async def cache_invalidate():
    """Manually invalidate cache to force refresh on next request."""
    invalidate_cache()
    return {
        "status": "success",
        "message": "Cache invalidated. Next request will refresh from database."
    }

import asyncio

@app.on_event("startup")
async def startup_event():
    """Initialize database tables and configurations on startup"""
    try:
        conn = get_connection()
        create_token_tables(conn)
        conn.close()
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.warning(f"Error initializing database tables: {e}")

def process_invoice_sync(file_path: str, companyID: str, username: str, licenceID: str = None, connection_params: str = None):
    from fastapi import UploadFile
    import os

    class DummyUploadFile:
        def __init__(self, path):
            self.file_path = path
            self.filename = os.path.basename(path)
            self.content_type = "application/octet-stream"
        async def read(self):
            with open(self.file_path, "rb") as f:
                return f.read()

    dummy_file = DummyUploadFile(file_path)

    coro = process_invoice(dummy_file, companyID, username, licenceID, connection_params)
    return asyncio.run(coro)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
