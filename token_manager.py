"""
Token Management Module
Handles token retrieval, validation, and usage logging
"""
import random
import logging
from datetime import datetime
from db_connection import get_connection

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages API tokens from TokenMaster table"""
    
    STATUS_ACTIVE = "Active"
    STATUS_EXPIRED = "Expired"
    STATUS_EXCEEDED = "Exceeded"
    STATUS_DISABLED = "Disabled"
    
    @staticmethod
    def get_active_token(company_id: str, connection=None):
        """
        Step1: Validate company exists in Company table using connection from db.
        Step2: Retrieve active token (ApiKey) from TokenMaster filtered by CompanyID and Status='Active'.
        Step3: Return token info (random if multiple) or structured null/error response. Other usage logging logic remains unchanged elsewhere.
        
        Args:
            company_id: The company ID to fetch token for
            connection: Database connection (optional, creates new if not provided)
            
        Returns:
            dict: Token info with TokenID, ApiKey, Provider, or error dict
        """
        # Clean company_id to remove any leading/trailing whitespace
        company_id = company_id.strip() if company_id else company_id
        
        if connection is None:
            try:
                connection = get_connection()
                logger.debug(f"Created new database connection for token lookup")
            except Exception as e:
                logger.error(f"Failed to create database connection: {e}")
                return {
                    "success": False,
                    "error": "connection_error",
                    "message": "Database connection failed. Please contact support."
                }
        
        try:
            cursor = connection.cursor()

            # Step1: Validate company exists
            try:
                cursor.execute("SELECT CompanyID FROM Company WHERE CompanyID = ?", (company_id,))
                comp = cursor.fetchone()
                if not comp:
                    logger.info(f"Company '{company_id}' not found in Company table")
                    return {
                        "success": False,
                        "token_id": None,
                        "api_key": None,
                        "provider": None,
                        "status": None,
                        "message": "Company ID not found.",
                        "error": "invalid_company",
                        "company_id": company_id
                    }
            except Exception as ce:
                logger.warning(f"Company table lookup failed (continuing token check): {ce}")
                # If table missing we still continue to token lookup

            # Step2: Fetch active tokens for company
            cursor.execute("""
                SELECT TokenID, ApiKey, Provider, Status, TotalTokenLimit
                FROM TokenMaster WHERE CompanyID = ? AND Status = ? ORDER BY CreatedAt DESC
            """, (company_id, TokenManager.STATUS_ACTIVE))
            active_tokens = cursor.fetchall()

            if not active_tokens:
                # Determine if any tokens exist with other status for messaging
                cursor.execute("SELECT DISTINCT Status FROM TokenMaster WHERE CompanyID = ?", (company_id,))
                statuses = [r[0] for r in cursor.fetchall()]
                if statuses:
                    if TokenManager.STATUS_EXPIRED in statuses:
                        msg = "Active token missing: existing token(s) are Expired."
                    elif TokenManager.STATUS_EXCEEDED in statuses:
                        msg = "Active token missing: existing token(s) exceeded usage limit."
                    elif TokenManager.STATUS_DISABLED in statuses:
                        msg = "Active token missing: existing token(s) are Disabled."
                    else:
                        msg = "Active token missing: tokens exist but none Active."
                else:
                    msg = "No tokens configured for this company."
                return {
                    "success": False,
                    "token_id": None,
                    "api_key": None,
                    "provider": None,
                    "status": None,
                    "message": msg,
                    "statuses_present": statuses,
                    "company_id": company_id
                }

            # Step3: Random active token selection
            token_row = random.choice(active_tokens)
            return {
                "success": True,
                "token_id": token_row[0],
                "api_key": token_row[1],
                "provider": token_row[2],
                "status": token_row[3],
                "total_limit": token_row[4],
                "company_id": company_id
            }

        except Exception as e:
            logger.error(f"Error fetching token for company {company_id}: {e}")
            return {
                "success": False,
                "token_id": None,
                "api_key": None,
                "provider": None,
                "status": None,
                "message": "Database error during token lookup.",
                "error": "database_error",
                "company_id": company_id
            }
    
    @staticmethod
    def check_token_status(company_id: str, connection=None):
        """
        Check token status for a company and return appropriate message.
        
        Args:
            company_id: The company ID to check
            connection: Database connection (optional)
            
        Returns:
            dict: Status information
        """
        if connection is None:
            connection = get_connection()
        
        try:
            cursor = connection.cursor()
            
            # Check for any token with specific statuses
            cursor.execute("""
                SELECT Status, COUNT(*) as count
                FROM TokenMaster
                WHERE CompanyID = ?
                GROUP BY Status
            """, (company_id,))
            
            statuses = cursor.fetchall()
            cursor.close()
            
            status_map = {row[0]: row[1] for row in statuses}
            
            # If no rows returned, company has no tokens at all
            if not status_map:
                return {
                    "has_error": True,
                    "status": "no_token",
                    "message": "No token available for your company. Please contact support."
                }
            
            if TokenManager.STATUS_EXPIRED in status_map:
                return {
                    "has_error": True,
                    "status": TokenManager.STATUS_EXPIRED,
                    "message": "Your AI token has expired. Please renew your subscription."
                }
            
            if TokenManager.STATUS_EXCEEDED in status_map or TokenManager.STATUS_DISABLED in status_map:
                return {
                    "has_error": True,
                    "status": TokenManager.STATUS_EXCEEDED if TokenManager.STATUS_EXCEEDED in status_map else TokenManager.STATUS_DISABLED,
                    "message": "Your AI token is no longer available or has been disabled. Please contact support."
                }
            
            if TokenManager.STATUS_ACTIVE not in status_map:
                return {
                    "has_error": True,
                    "status": "no_token",
                    "message": "No token available for your company. Please contact support."
                }
            
            return {
                "has_error": False,
                "status": TokenManager.STATUS_ACTIVE,
                "message": "Token is active"
            }
        
        except Exception as e:
            logger.error(f"Error checking token status for company {company_id}: {e}")
            return {
                "has_error": True,
                "status": "error",
                "message": "Failed to check token status"
            }
    
    @staticmethod
    def log_token_usage(token_id: int, usage_info: dict, branch: str = None, 
                       requested_by: str = None, connection=None):
        """
        Log token usage to TokenUsageLogs and update TokenUsageSummary.
        
        Args:
            token_id: The TokenID
            usage_info: Dict with keys: input_tokens, output_tokens, text_prompt_tokens,
                       image_prompt_tokens, text_candidates_tokens, requests
            branch: Branch/division name
            requested_by: Username who made the request
            connection: Database connection (optional)
            
        Returns:
            dict: Success/error status
        """
        if connection is None:
            connection = get_connection()
        
        try:
            cursor = connection.cursor()
            
            input_tokens = usage_info.get('input_tokens', 0)
            output_tokens = usage_info.get('output_tokens', 0)
            text_prompt_tokens = usage_info.get('text_prompt_tokens', 0)
            image_prompt_tokens = usage_info.get('image_prompt_tokens', 0)
            text_candidates_tokens = usage_info.get('text_candidates_tokens', 0)
            request_count = usage_info.get('requests', 1)
            
            total_tokens = input_tokens + output_tokens
            
            # Insert into TokenUsageLogs
            cursor.execute("""
                INSERT INTO TokenUsageLogs 
                (TokenID, Branch, RequestedBy, InputTokens, OutputTokens, 
                 TextPromptTokens, ImagePromptTokens, TextCandidatesTokens, 
                 TotalTokensUsed, RequestCount, LoggedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, (
                token_id, branch or 'Default', requested_by or 'System',
                input_tokens, output_tokens, text_prompt_tokens,
                image_prompt_tokens, text_candidates_tokens,
                total_tokens, request_count
            ))
            connection.commit()
            
            # Update or insert into TokenUsageSummary
            cursor.execute("""
                SELECT SummaryID, TotalUsedTokens, TotalRemainingTokens
                FROM TokenUsageSummary
                WHERE TokenID = ?
            """, (token_id,))
            
            summary_row = cursor.fetchone()
            
            if summary_row:
                summary_id = summary_row[0]
                existing_used = summary_row[1]
                existing_remaining = summary_row[2]
                
                new_used = existing_used + total_tokens
                new_remaining = existing_remaining - total_tokens
                
                cursor.execute("""
                    UPDATE TokenUsageSummary
                    SET TotalUsedTokens = ?, TotalRemainingTokens = ?, LastUpdated = GETDATE()
                    WHERE SummaryID = ?
                """, (new_used, new_remaining, summary_id))
            else:
                # Get total limit from TokenMaster
                cursor.execute("""
                    SELECT TotalTokenLimit
                    FROM TokenMaster
                    WHERE TokenID = ?
                """, (token_id,))
                
                limit_row = cursor.fetchone()
                total_limit = limit_row[0] if limit_row else 100000
                
                new_used = total_tokens
                new_remaining = total_limit - total_tokens
                
                cursor.execute("""
                    INSERT INTO TokenUsageSummary
                    (TokenID, TotalUsedTokens, TotalRemainingTokens, LastUpdated)
                    VALUES (?, ?, ?, GETDATE())
                """, (token_id, new_used, new_remaining))
            
            connection.commit()
            cursor.close()
            
            logger.info(f"Token {token_id} usage logged: {total_tokens} tokens used")
            
            return {
                "success": True,
                "message": "Usage logged successfully"
            }
        
        except Exception as e:
            logger.error(f"Error logging token usage for token {token_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to log token usage: {str(e)}"
            }
    
    @staticmethod
    def extract_usage_from_log(log_line: str):
        """
        Extract token usage from Gemini log line.
        
        Expected format:
        INFO:api:Gemini processing complete. Usage: RunUsage(input_tokens=2518, output_tokens=652, 
                    details={'text_prompt_tokens': 712, 'image_prompt_tokens': 1806, 
                    'text_candidates_tokens': 652}, requests=1)
        
        Args:
            log_line: The log line containing usage information
            
        Returns:
            dict: Extracted usage info or None if parsing fails
        """
        try:
            import re
            
            # Extract input_tokens
            input_match = re.search(r'input_tokens=(\d+)', log_line)
            input_tokens = int(input_match.group(1)) if input_match else 0
            
            # Extract output_tokens
            output_match = re.search(r'output_tokens=(\d+)', log_line)
            output_tokens = int(output_match.group(1)) if output_match else 0
            
            # Extract text_prompt_tokens
            text_prompt_match = re.search(r"'text_prompt_tokens':\s*(\d+)", log_line)
            text_prompt_tokens = int(text_prompt_match.group(1)) if text_prompt_match else 0
            
            # Extract image_prompt_tokens
            image_prompt_match = re.search(r"'image_prompt_tokens':\s*(\d+)", log_line)
            image_prompt_tokens = int(image_prompt_match.group(1)) if image_prompt_match else 0
            
            # Extract text_candidates_tokens
            text_cand_match = re.search(r"'text_candidates_tokens':\s*(\d+)", log_line)
            text_candidates_tokens = int(text_cand_match.group(1)) if text_cand_match else 0
            
            # Extract requests
            requests_match = re.search(r'requests=(\d+)', log_line)
            requests = int(requests_match.group(1)) if requests_match else 1
            
            return {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'text_prompt_tokens': text_prompt_tokens,
                'image_prompt_tokens': image_prompt_tokens,
                'text_candidates_tokens': text_candidates_tokens,
                'requests': requests
            }
        
        except Exception as e:
            logger.error(f"Error parsing usage from log line: {e}")
            return None
