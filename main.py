import os
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Setup Environment Variables from Railway/Local .env
BREVO_API_KEY = os.getenv('BREVO_API_KEY')
BREVO_URL = 'https://api.brevo.com/v3/contacts'

@app.get("/")
def read_root():
    return {"status": "online", "message": "Neuraflux Backend is Live!"}

# ENDPOINT 1: For Cal.com Bookings (Sequence A)
@app.post('/api/audit-booked')
async def audit_booked(request: Request):
    data = await request.json()
    payload = data.get('payload', {})
    email = payload.get('email', '')
    first_name = payload.get('firstName', '')

    requests.post(BREVO_URL, json={
        'email': email,
        'attributes': {'FIRSTNAME': first_name, 'sequence': 'A'},
        'updateEnabled': True
    }, headers={
        'api-key': BREVO_API_KEY,
        'Content-Type': 'application/json'
    })
    return {'status': 'ok'}

# ENDPOINT 2: For Chatbot/Email Capture (Sequence B)
class EmailCapture(BaseModel):
    email: str
    first_name: str = ''

@app.post('/api/email-capture')
async def email_capture(body: EmailCapture):
    requests.post(BREVO_URL, json={
        'email': body.email,
        'attributes': {'FIRSTNAME': body.first_name, 'sequence': 'B'},
        'updateEnabled': True
    }, headers={
        'api-key': BREVO_API_KEY,
        'Content-Type': 'application/json'
    })
    return {'status': 'ok'}