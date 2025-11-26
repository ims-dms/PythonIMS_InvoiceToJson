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

# CORS configuration - Fixed for browser requests with Authorization headers
origins = [
    "http://localhost:4100",
    "http://localhost:8080",
    "http://127.0.0.1:4100",
    "http://127.0.0.1:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
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
Extract data from ALL PAGES of the TAX INVOICE document following these strict rules. Combine information from all provided images/pages into a single cohesive JSON output:
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
   - Extract ALL SKUs from the "Description" column across ALL pages. It is very important to ensure that Description values are accurately extracted from the invoice.
   - Extract SKU codes separately as "sku_code" across ALL pages. It is very important to ensure that SKU code values are accurately extracted from the invoice.
   - Extract corresponding numbers from the "Quantity", "Shortage", "Breakage", "Leakage", "Batch", "SNO", "Rate", "Discount", "MRP", "VAT", "HSCode", "AltQty", and "Unit" columns across ALL pages.
   - HSCode is very important; ensure HSCode values are accurately extracted from the invoice across ALL pages.
   - Maintain array order consistency across all product-related fields, aggregating from all pages

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
   - Return empty strings/arrays for missing data
   - ABSOLUTELY NO ADDITIONAL TEXT OR MARKDOWN
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
    array_fields = ['sku', 'quantity', 'shortage', 'breakage', 'leakage', 'hscode', 'altQty', 'unit', 'discount', 'sno']
    max_length = max(len(data.get(field, [])) for field in array_fields)
    
    for field in array_fields:
        if len(data.get(field, [])) != max_length:
            if field in ['quantity', 'shortage', 'breakage', 'leakage', 'altQty', 'discount']:
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
            else:
                media_type = content_type or 'application/octet-stream'
                binary_contents.append(BinaryContent(file_content, media_type=media_type))
            
            # Build agent inputs
            agent_inputs = [PROCESSING_PROMPT] + binary_contents
            
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
            logger.info(f"Gemini response length: {len(raw_response)} chars")
            
            try:
                # Parse JSON response
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1).strip()
                    logger.info("Found JSON in markdown code block")
                else:
                    json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0).strip()
                        logger.info("Found raw JSON object")
                    else:
                        logger.error(f"No JSON found in response")
                        raise ValueError(f"No JSON found in Gemini response")
                
                data = json.loads(json_str)
                logger.info(f"Successfully parsed JSON with {len(data)} top-level keys")
                
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
                
                # Process products
                products = []
                sku_list = data.get('sku', [])
                sku_code_list = data.get('sku_code', [])
                quantity_list = data.get('quantity', [])
                shortage_list = data.get('shortage', [])
                breakage_list = data.get('breakage', [])
                leakage_list = data.get('leakage', [])
                batch_list = normalized_data.get('batch') or []
                sno_list = data.get('sno', [])
                rate_list = normalized_data.get('rate') or []
                discount_list = data.get('discount', [])
                mrp_list = normalized_data.get('mrp') or normalized_data.get('mrpvalue') or []
                vat_list = normalized_data.get('vat') or normalized_data.get('vatvalue') or []
                hscode_list = normalized_data.get('hscode') or normalized_data.get('hs_code') or []
                altqty_list = normalized_data.get('altqty') or normalized_data.get('altquantity') or []
                unit_list = normalized_data.get('unit') or normalized_data.get('unitofmeasure') or normalized_data.get('uom') or []
                
                max_len = max(
                    len(sku_list), len(sku_code_list), len(quantity_list), len(shortage_list),
                    len(breakage_list), len(leakage_list), len(batch_list),
                    len(sno_list), len(rate_list), len(discount_list),
                    len(mrp_list), len(vat_list), len(hscode_list),
                    len(altqty_list), len(unit_list)
                )
                
                for i in range(max_len):
                    product = {
                        "sku": sku_list[i] if i < len(sku_list) else "",
                        "sku_code": sku_code_list[i] if i < len(sku_code_list) else "",
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
                    products.append(product)
                
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
                        SELECT m.desca, m.mcode, m.menucode, a.BASEUOM as baseunit, a.CONFACTOR, a.altunit 
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
                
                db_conn.close()
                
                # Clean up response data
                for key in ['sku', 'quantity', 'shortage', 'breakage', 'leakage', 'batch', 'sno', 'rate', 'discount', 'mrp', 'vat', 'brands']:
                    data.pop(key, None)
                
                data['products'] = products
                
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
