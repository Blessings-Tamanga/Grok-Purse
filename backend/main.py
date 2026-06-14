import os
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
    title="MomoPulse API",
    description="AI-powered Mobile Money Intelligence System",
    version="2.0.0"
)

# FIX: Ensure DB is always created in the same folder as main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'momopulse.db')

# =========================================================
# 2. PYDANTIC MODELS
# =========================================================
class SMSIngestRequest(BaseModel):
    sms_text: str
    user_phone: str = "265888123456"

# =========================================================
# 3. DATABASE LAYER
# =========================================================
def init_db():
    conn = sqlite3.connect(DB_PATH) # <-- UPDATED PATH
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_phone TEXT, amount REAL, tx_type TEXT, 
                  vendor TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

init_db()

# ... [Keep the rest of your parse_momo_sms, insert_transaction, and execute_sql_query functions exactly the same] ...

# ... [Keep your AI Layer and API Routes exactly the same] ...