import re
import sqlite3
import asyncio
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import ollama
from twilio.twiml.messaging_response import MessagingResponse

# =========================================================
# 1. FASTAPI INITIALIZATION & CONFIG
# =========================================================
app = FastAPI(
    title="GrokPulse API",
    description="AI-powered Mobile Money Intelligence System",
    version="2.0.0"
)

# =========================================================
# 2. PYDANTIC MODELS (Strict Data Validation)
# =========================================================
class SMSIngestRequest(BaseModel):
    sms_text: str
    user_phone: str = "265888123456" # Default test user

class ParsedTransaction(BaseModel):
    amount: float
    tx_type: str
    vendor: str

# =========================================================
# 3. DATABASE LAYER (Sync, but run in thread pool by FastAPI)
# =========================================================
def init_db():
    conn = sqlite3.connect('GrokPulse.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_phone TEXT, amount REAL, tx_type TEXT, 
                  vendor TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

init_db()

def parse_momo_sms(sms_text: str):
    """Hardened Regex parser. No LLMs allowed for financial extraction."""
    amount, tx_type, vendor = 0.0, None, "Unknown"

    match_income = re.search(r"received MK\s*([\d,]+\.?\d*)", sms_text, re.IGNORECASE)
    if match_income:
        amount = float(match_income.group(1).replace(',', ''))
        tx_type = "income"
        vendor_match = re.search(r"from\s+(.+)", sms_text, re.IGNORECASE)
        if vendor_match: vendor = vendor_match.group(1).strip()

    match_expense = re.search(r"paid MK\s*([\d,]+\.?\d*)", sms_text, re.IGNORECASE)
    if match_expense:
        amount = float(match_expense.group(1).replace(',', ''))
        tx_type = "expense"
        vendor_match = re.search(r"to\s+(.+)", sms_text, re.IGNORECASE)
        if vendor_match: vendor = vendor_match.group(1).strip()

    if tx_type:
        return {"amount": amount, "tx_type": tx_type, "vendor": vendor}
    return None

def insert_transaction(user_phone: str, parsed_data: dict):
    conn = sqlite3.connect('GrokPulse.db')
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_phone, amount, tx_type, vendor, timestamp) VALUES (?, ?, ?, ?, datetime('now'))",
              (user_phone, parsed_data['amount'], parsed_data['tx_type'], parsed_data['vendor']))
    conn.commit()
    conn.close()

def execute_sql_query(sql: str):
    try:
        conn = sqlite3.connect('GrokPulse.db')
        c = conn.cursor()
        c.execute(sql)
        result = c.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        print(f"SQL Execution Error: {e}")
        return None

# =========================================================
# 4. AI LAYER (Async Qwen/Llama via Ollama)
# =========================================================
async def get_sql_from_prompt(user_question: str):
    """
    Translates natural language to SQL using LOCAL open-source LLM.
    Uses Ollama's AsyncClient to prevent blocking the FastAPI event loop.
    """
    prompt = f"""
    You are an expert SQLite SQL generator.
    Table: transactions (id INTEGER, user_phone TEXT, amount REAL, tx_type TEXT, vendor TEXT, timestamp DATETIME).
    
    User question: "{user_question}"
    
    Generate a single, valid SQLite query to answer this. 
    Assume the user_phone is '265888123456'.
    Output ONLY the raw SQL statement. No markdown, no explanations.
    """
    
    try:
        # Initialize async Ollama client
        client = ollama.AsyncClient()
        response = await client.chat(model='qwen2.5:7b', messages=[
            {'role': 'user', 'content': prompt}
        ])
        
        sql = response['message']['content'].strip()
        return sql.replace("```sql", "").replace("```", "").strip()
    
    except Exception as e:
        print(f"Local LLM Error: {e}")
        return None

def format_response(user_question: str, result_value):
    if result_value is None:
        return "Sorry, I couldn't process that. Try asking 'What is my balance?'"
    
    if "balance" in user_question.lower():
        return f"Based on detected MoMo activity, your current Mobile Money Pulse is MK {result_value:,.2f}."
    elif "spend" in user_question.lower() or "spent" in user_question.lower():
        return f"Based on detected MoMo activity, your total expenses are MK {result_value:,.2f}."
    else:
        return f"Based on detected MoMo activity, the calculated amount is MK {result_value:,.2f}."

# =========================================================
# 5. API ROUTES
# =========================================================

@app.post("/ingest_sms")
def ingest_sms(payload: SMSIngestRequest):
    """
    Endpoint for Android App to send parsed SMS/WhatsApp notifications.
    FastAPI automatically validates the JSON against SMSIngestRequest.
    """
    parsed = parse_momo_sms(payload.sms_text)
    if parsed:
        insert_transaction(payload.user_phone, parsed)
        return {"status": "success", "parsed_data": parsed}
    return {"status": "ignored", "reason": "Not a recognized MoMo SMS"}

@app.post("/whatsapp_webhook")
def whatsapp_webhook(Body: str = Form(...), From: str = Form(...)):
    """
    Twilio WhatsApp Webhook. 
    NOTE: Twilio sends Form-Encoded data, NOT JSON. 
    We use FastAPI's Form(...) to extract it.
    """
    user_question = Body.strip()
    sender_phone = From.replace('whatsapp:', '')

    # 1. Translate to SQL using Async Qwen
    # We use asyncio.run to call the async function from a sync endpoint
    sql = asyncio.run(get_sql_from_prompt(user_question))
    
    if not sql:
        final_response = "I couldn't understand that. Please try asking about your balance or spending."
    else:
        # 2. Execute SQL (Deterministic Math)
        result_value = execute_sql_query(sql)
        # 3. Format with False Precision Guardrails
        final_response = format_response(user_question, result_value)

    # 4. Return TwiML response to Twilio
    resp = MessagingResponse()
    resp.message(final_response)
    
    # CRITICAL FASTAPI GOTCHA: Twilio expects XML, FastAPI defaults to JSON.
    # We must explicitly return an XML Response.
    return Response(content=str(resp), media_type="application/xml")

@app.get("/")
def home():
    return {"message": "GrokPulse API is running 🚀", "docs": "/docs"}