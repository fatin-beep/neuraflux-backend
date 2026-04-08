import os
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
app = FastAPI()

# 1. Setup Environment Variables
BREVO_API_KEY = os.getenv('BREVO_API_KEY')
BREVO_URL = 'https://api.brevo.com/v3/contacts'
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- DATA MODELS ---
class LeadCapture(BaseModel):
    name: str        
    email: str       
    business: str    
    challenge: str   

class ChatSession(BaseModel):
    flow: str
    email: str
    messages: dict   

# --- HEALTH CHECK ---
@app.get("/")
def read_root():
    return {"status": "online", "message": "Neuraflux Backend Synced & Fully Operational!"}

# --- ENDPOINT 1: For Cal.com / Calendly (Sarmad's Sequence A) ---
@app.post('/api/audit-booked')
async def audit_booked(request: Request):
    try:
        data = await request.json()
        payload = data.get('payload', {})
        email = payload.get('email', '')
        first_name = payload.get('firstName', '')

        # Log to Sarmad's 'contacts' table
        supabase.table("contacts").insert({
            "email": email,
            "first_name": first_name,
            "sequence": "A"
        }).execute()

        return {'status': 'ok', 'message': 'Calendly booking logged'}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- ENDPOINT 2: Website Form (Hamza's 'Leads' Table + Sequence B) ---
@app.post('/api/email-capture')
async def email_capture(body: LeadCapture):
    try:
        # 1. Insert into Hamza's 'Leads' table
        supabase.table("Leads").insert({
            "name": body.name,
            "email": body.email,
            "business": body.business,
            "challenge": body.challenge
        }).execute()

        # 2. Trigger Brevo Sequence B
        requests.post(BREVO_URL, json={
            'email': body.email,
            'attributes': {'FIRSTNAME': body.name, 'sequence': 'B'},
            'updateEnabled': True
        }, headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json'})

        return {'status': 'ok', 'message': 'Lead saved to Leads table'}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- ENDPOINT 3: Chatbot (Hamza's 'Chat_sessions' Table + Sequence B) ---
@app.post('/api/chat/session')
async def save_chat(body: ChatSession):
    try:
        # 1. Insert into 'Chat_sessions' table
        supabase.table("Chat_sessions").insert({
            "flow": body.flow,
            "email": body.email,
            "messages": body.messages
        }).execute()

        # 2. Trigger Brevo if email is provided
        if body.email:
            requests.post(BREVO_URL, json={
                'email': body.email,
                'attributes': {'sequence': 'B'},
                'updateEnabled': True
            }, headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json'})

        return {'status': 'ok', 'message': 'Session saved to Chat_sessions'}
    except Exception as e:
        return {"status": "error", "message": str(e)}