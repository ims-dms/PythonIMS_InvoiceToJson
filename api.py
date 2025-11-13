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
from db_connection import get_connection
from fuzzy_matcher import match_ocr_products, format_api_response, minimize_error_message, api_error_response
from menu_cache import get_cached_menu_items, get_cache_stats, invalidate_cache

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

# Initialize Gemini

# Read GEMINI_API_KEY from appSetting.txt
def read_api_key_from_file(file_path='appSetting.txt'):
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if line.startswith('GEMINI_API_KEY='):
                    return line.split('=', 1)[1].strip()
    except Exception as e:
        raise RuntimeError(f"Failed to read API key from {file_path}: {e}")
    raise ValueError("GEMINI_API_KEY not found in appSetting.txt")

GEMINI_API_KEY = read_api_key_from_file()

provider = GoogleGLAProvider(api_key=GEMINI_API_KEY)
model = GeminiModel('gemini-2.0-flash-lite', provider=provider)
gemini_agent = Agent(model)

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
    file: UploadFile = File(None),
    companyID: str = Form(...),
    username: str = Form(...),
    licenceID: str = Form(None),
    connection_params: str = Form(None),  # New parameter for connection parameters as JSON string
    extractFromLink: int = Form(0),
    pdf_url: str = Form(None)
):
    if not companyID or not username:
        return format_api_response(
            message="Please provide both companyID and username.",
            status="error"
        )
    
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
            file_name = pdf_url.split('/')[-1].split('?')[0]  # Extract filename from URL
            content_type = "application/pdf"  # Assume PDF
        except requests.RequestException as e:
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

    try:
        # Handle PDFs (convert all pages to images) or other single binary attachments
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
            # Use the first page's base64 for any logging/preview purposes
            first_img_bytes, first_media = images[0]
            image_base64 = base64.b64encode(first_img_bytes).decode('utf-8')
            for img_bytes, media in images:
                binary_contents.append(BinaryContent(img_bytes, media_type=media))
        else:
            media_type = content_type or 'application/octet-stream'
            image_base64 = base64.b64encode(file_content).decode('utf-8')
            binary_contents.append(BinaryContent(file_content, media_type=media_type))

        # Build agent inputs: prompt followed by all BinaryContent attachments (one per page)
        agent_inputs = [PROCESSING_PROMPT] + binary_contents
        logger.info(f"Sending {len(binary_contents)} images to Gemini for processing")

        result = await gemini_agent.run(agent_inputs)
        usage = result.usage()
        usage_info = f"Gemini processing complete. Usage: {usage}"
        logger.info(usage_info)

        # Extract the actual response text from the result
        # pydantic_ai AgentRunResult has 'output' attribute, not 'data'
        raw_response = result.output if hasattr(result, 'output') else str(result)
        logger.info(f"Gemini response length: {len(raw_response)} chars")
        logger.info(f"First 500 chars of response: {raw_response[:500]}")

        try:
            # Try to parse the response as JSON
            # First, try to extract JSON from markdown code blocks (Gemini often wraps in ```json ... ```)
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
                logger.info(f"Found JSON in markdown code block")
            else:
                # Try to find raw JSON object (match outer braces with everything inside)
                json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0).strip()
                    logger.info(f"Found raw JSON object")
                else:
                    logger.error(f"No JSON found in response. Full response: {raw_response}")
                    raise ValueError(f"No JSON found in Gemini response. Response preview: {raw_response[:500]}")
            
            logger.debug(f"JSON string to parse (first 300 chars): {json_str[:300]}")
            data = json.loads(json_str)
            logger.info(f"Successfully parsed JSON with {len(data)} top-level keys: {list(data.keys())[:10]}")

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

            # Fetch menu items using intelligent caching (critical for 700k items)
            import json as json_lib
            
            def fetch_menu_items_from_db():
                """Fetch menu items from database - only called on cache miss."""
                if connection_params:
                    try:
                        conn_params_dict = json_lib.loads(connection_params)
                    except Exception as e:
                        raise ValueError(f"Invalid connection_params JSON: {str(e)}")
                    conn = get_connection(conn_params_dict)
                else:
                    conn = get_connection()
                
                cursor = conn.cursor()
                cursor.execute("SELECT desca, mcode FROM menuitem where type = 'A'")
                items = cursor.fetchall()
                cursor.close()
                conn.close()
                return items
            
            # Get menu items (from cache if available, otherwise fetch from DB)
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
            supplier_name = data.get('company_name', '')
            products = match_ocr_products(
                ocr_products=products,
                menu_items=menu_items,
                top_k=3,  # Return top 3 suggestions per product
                score_cutoff=60.0,  # Minimum match score of 60%
                connection=db_conn,
                supplier_name=supplier_name
            )
            logger.info("Fuzzy matching completed successfully")

            # Close the connection
            db_conn.close()

            for key in ['sku', 'quantity', 'shortage', 'breakage', 'leakage', 'batch', 'sno', 'rate', 'discount', 'mrp', 'vat', 'brands']:
                data.pop(key, None)

            data['products'] = products

            # Remove unwanted top-level fields as per user request
            for key in ['sku_code', 'hscode', 'altQty', 'unit', 'full_sku_names']:
                data.pop(key, None)

            # Return success response with proper status
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
        
        # Return formatted error response with minimized user message
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
