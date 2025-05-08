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
from rapidfuzz import process
from db_connection import get_connection

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Tax Invoice Processor", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY in environment variables")

provider = GoogleGLAProvider(api_key=GEMINI_API_KEY)
model = GeminiModel('gemini-2.0-flash-lite', provider=provider)
gemini_agent = Agent(model)

PROCESSING_PROMPT = """
Extract data from TAX INVOICE document following these strict rules:
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
   - Extract ALL SKUs from the "Description" column. It is very important to ensure that Description values are accurately extracted from the invoice.
   - Extract SKU codes separately as "sku_code". It is very important to ensure that SKU code values are accurately extracted from the invoice.
   - Extract corresponding numbers from the "Quantity", "Shortage", "Breakage", "Leakage", "Batch", "SNO", "Rate", "Discount", "MRP", "VAT", "HSCode", "AltQty", and "Unit" columns.
   - HSCode is very important; ensure HSCode values are accurately extracted from the invoice.
   - Maintain array order consistency across all product-related fields

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
    file: UploadFile = File(...),
    companyID: str = Form(...),
    username: str = Form(...),
    licenceID: str = Form(None),
    connection_params: str = Form(None)  # New parameter for connection parameters as JSON string
):
    if not companyID or not username:
        return {"error": "Please provide both companyID and username."}
    try:
        file_content = await file.read()

        if file.content_type == "application/pdf":
            images = convert_from_bytes(file_content, first_page=1, last_page=1)
            img_byte_arr = BytesIO()
            images[0].save(img_byte_arr, format='PNG')
            file_content = img_byte_arr.getvalue()
            media_type = 'image/png'
        else:
            media_type = file.content_type or 'application/octet-stream'

        image_base64 = base64.b64encode(file_content).decode('utf-8')

        result = await gemini_agent.run([PROCESSING_PROMPT, BinaryContent(file_content, media_type=media_type)])
        usage = result.usage()
        usage_info = f"Gemini processing complete. Usage: {usage}"
        logger.info(usage_info)

        raw_response = str(result.data)
        logger.debug(f"Raw Gemini response: {raw_response}")

        try:
            if hasattr(result, 'data') and isinstance(result.data, dict):
                data = result.data
            else:
                json_match = re.search(r'({.*})', raw_response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(1))
                else:
                    raise ValueError("No JSON found in response")

            logger.debug(f"Keys in response data: {list(data.keys())}")

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

            for key in ['sku', 'quantity', 'shortage', 'breakage', 'leakage', 'batch', 'sno', 'rate', 'discount', 'mrp', 'vat', 'brands']:
                data.pop(key, None)

            # Connect to DB and fetch desca and mcode list
            import json as json_lib
            if connection_params:
                try:
                    conn_params_dict = json_lib.loads(connection_params)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid connection_params JSON: {str(e)}")
                conn = get_connection(conn_params_dict)
            else:
                conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT desca, mcode FROM menuitem")
            menu_items = cursor.fetchall()  # list of tuples (desca, mcode)
            cursor.close()
            conn.close()

            desca_list = [item[0] for item in menu_items]

            # For each product, find nearest match from desca_list using RapidFuzz with score cutoff 80
            for product in products:
                sku_name = product.get("sku", "")
                if sku_name:
                    best_match = process.extractOne(sku_name, desca_list, score_cutoff=80)
                    if best_match:
                        matched_desca = best_match[0]
                        # Find corresponding mcode
                        matched_mcode = next((item[1] for item in menu_items if item[0] == matched_desca), "")
                        product["NearMappedItem"] = {"desca": matched_desca, "mcode": matched_mcode}
                    else:
                        product["NearMappedItem"] = {"desca": "", "mcode": ""}
                else:
                    product["NearMappedItem"] = {"desca": "", "mcode": ""}

            data['products'] = products

            # Remove unwanted top-level fields
            for key in ['sku_code', 'hscode', 'altQty', 'unit', 'full_sku_names']:
                data.pop(key, None)

            # Insert success record in tblOCRTokenDetails
            from datetime import date, datetime as dt
            current_date = date.today()
            current_time = dt.now().time()

            import json as json_lib
            if connection_params:
                try:
                    conn_params_dict = json_lib.loads(connection_params)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid connection_params JSON: {str(e)}")
                conn = get_connection(conn_params_dict)
            else:
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
                Remarks VARCHAR(MAX),
                JSONData VARCHAR(MAX)
            )
            """
            cursor.execute(create_table_sql)
            insert_sql = """
            INSERT INTO tblOCRTokenDetails (CompanyId, Username, LicenceID, Requests, RequestTokens, ResponseTokens, TotalTokens, Date, Time, Status, Remarks, JSONData)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(insert_sql, (
                companyID,
                username,
                licenceID,
                usage.requests,
                usage.request_tokens,
                usage.response_tokens,
                usage.total_tokens,
                current_date,
                current_time,
                "Success",
                "",
                json.dumps(data)
            ))
            conn.commit()
            cursor.close()
            conn.close()

            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Processing error: {str(e)}")
            raise HTTPException(
                status_code=422,
                detail=f"Failed to process invoice: {str(e)}"
            )

            logger.debug(f"Keys in response data: {list(data.keys())}")

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

            for key in ['sku', 'quantity', 'shortage', 'breakage', 'leakage', 'batch', 'sno', 'rate', 'discount', 'mrp', 'vat', 'brands']:
                data.pop(key, None)

            # Connect to DB and fetch desca and mcode list
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT desca, mcode FROM menuitem")
            menu_items = cursor.fetchall()  # list of tuples (desca, mcode)
            cursor.close()
            conn.close()

            desca_list = [item[0] for item in menu_items]

            # For each product, find nearest match from desca_list using RapidFuzz with score cutoff 80
            for product in products:
                sku_name = product.get("sku", "")
                if sku_name:
                    best_match = process.extractOne(sku_name, desca_list, score_cutoff=80)
                    if best_match:
                        matched_desca = best_match[0]
                        # Find corresponding mcode
                        matched_mcode = next((item[1] for item in menu_items if item[0] == matched_desca), "")
                        product["NearMappedItem"] = {"desca": matched_desca, "mcode": matched_mcode}
                    else:
                        product["NearMappedItem"] = {"desca": "", "mcode": ""}
                else:
                    product["NearMappedItem"] = {"desca": "", "mcode": ""}

            data['products'] = products

            # Remove unwanted top-level fields as per user request
            for key in ['sku_code', 'hscode', 'altQty', 'unit', 'full_sku_names']:
                data.pop(key, None)

            return data

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Processing error: {str(e)}")
            raise HTTPException(
                status_code=422,
                detail=f"Failed to process invoice: {str(e)}"
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
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/")
async def health_check():
    return {
        "status": "active",
        "version": app.version,
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
