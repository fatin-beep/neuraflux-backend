import os
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
app = FastAPI()

# 1. Setup Environment Variables (Ensure these are in Railway Variables)
BREVO_API_KEY = os.getenv('BREVO_API_KEY')
BREVO_URL = 'https://api.brevo.com/v3/contacts'

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- DATA MODELS ---
class EmailCapture(BaseModel):
    email: str
    first_name: str
    business: str = "N/A"
    challenge: str = "N/A"

@app.get("/")
def read_root():
    return {"status": "online", "message": "Neuraflux Backend is Live!"}

# --- ENDPOINT 1: For Cal.com Bookings (Sarmad's Sequence A) ---
@app.post('/api/audit-booked')
async def audit_booked(request: Request):
    data = await request.json()
    payload = data.get('payload', {})
    email = payload.get('email', '')
    first_name = payload.get('firstName', '')

    # Log to 'contacts' table for backup
    supabase.table("contacts").insert({
        "email": email,
        "first_name": first_name,
        "sequence": "A"
    }).execute()

    return {'status': 'ok'}

# --- ENDPOINT 2: For Website Form (Hamza's DB + Sarmad's Sequence B) ---
@app.post('/api/email-capture')
async def email_capture(body: EmailCapture):
    # 1. Log to Hamza's 'Leads' table 
    # Note: We map 'first_name' to the 'name' column Hamza created
    supabase.table("Leads").insert({
        "name": body.first_name,
        "email": body.email,
        "business": body.business,
        "challenge": body.challenge
    }).execute()

    # 2. Log to 'contacts' table (Sarmad's email backup)
    supabase.table("contacts").insert({
        "email": body.email,
        "first_name": body.first_name,
        "sequence": "B"
    }).execute()

    # 3. Trigger Brevo Automation
    requests.post(BREVO_URL, json={
        'email': body.email,
        'attributes': {'FIRSTNAME': body.first_name, 'sequence': 'B'},
        'updateEnabled': True
    }, headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json'})

    return {'status': 'ok'}