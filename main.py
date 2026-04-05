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
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.get("/")
def read_root():
    return {"status": "online", "message": "Neuraflux Backend is Live!"}

# --- ENDPOINT 1: For Cal.com Bookings (Sequence A) ---
@app.post('/api/audit-booked')
async def audit_booked(request: Request):
    data = await request.json()
    payload = data.get('payload', {})
    email = payload.get('email', '')
    first_name = payload.get('firstName', '')

    # [span_2](start_span)[span_3](start_span)A. Add to Brevo with sequence=A[span_2](end_span)[span_3](end_span)
    requests.post(BREVO_URL, json={
        'email': email,
        'attributes': {'FIRSTNAME': first_name, 'sequence': 'A'},
        'updateEnabled': True
    }, headers={
        'api-key': BREVO_API_KEY,
        'Content-Type': 'application/json'
    })

    # [span_4](start_span)B. Log to Supabase contacts table for Hamza[span_4](end_span)
    supabase.table("contacts").insert({
        "email": email,
        "first_name": first_name,
        "sequence": "A"
    }).execute()

    return {'status': 'ok'}

# --- ENDPOINT 2: For Chatbot/Email Capture (Sequence B) ---
class EmailCapture(BaseModel):
    email: str
    first_name: str = ''

@app.post('/api/email-capture')
async def email_capture(body: EmailCapture):
    # [span_5](start_span)A. Add to Brevo with sequence=B[span_5](end_span)
    requests.post(BREVO_URL, json={
        'email': body.email,
        'attributes': {'FIRSTNAME': body.first_name, 'sequence': 'B'},
        'updateEnabled': True
    }, headers={
        'api-key': BREVO_API_KEY,
        'Content-Type': 'application/json'
    })

    # [span_6](start_span)[span_7](start_span)B. Log to Supabase contacts table for Hamza[span_6](end_span)[span_7](end_span)
    supabase.table("contacts").insert({
        "email": body.email,
        "first_name": body.first_name,
        "sequence": "B"
    }).execute()

    return {'status': 'ok'}