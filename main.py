import os
import hmac
import hashlib
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# Initialize clients
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = os.getenv("BREVO_API_KEY")
api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

class ContactForm(BaseModel):
    name: str
    email: EmailStr
    business: str
    challenge: str

class ChatEmail(BaseModel):
    email: EmailStr
    name: str = "Chat User"
    flow: str = "B"

def verify_cal_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature: return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

# Re-written to match Sarmad's exact SDK requirement
def add_to_brevo(email: str, first_name: str, list_id: int):
    try:
        create_contact = sib_api_v3_sdk.CreateContact(
            email=email,
            attributes={"FIRSTNAME": first_name},
            list_ids=[list_id],
            update_enabled=True
        )
        api_instance.create_contact(create_contact)
    except ApiException as e:
        print(f"Brevo API Error: {e}")
    except Exception as e:
        print(f"General Error: {e}")

@app.get('/api/health')
def health():
    return {'status': 'ok'}

@app.post('/api/contact')
async def contact_form(body: ContactForm):
    try:
        supabase.table("Leads").insert({
            "name": body.name, "email": body.email, "business": body.business,
            "challenge": body.challenge, "source": "form", "sequence": "B"
        }).execute()
        add_to_brevo(body.email, body.name, 6)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# UPDATED: Sarmad's logic for Audit Booked
@app.post('/api/audit-booked')
async def audit_booked(request: Request):
    try:
        body_bytes = await request.body()
        signature = request.headers.get("X-Cal-Signature-256")
        
        # Verify Webhook Signature
        if not verify_cal_signature(body_bytes, signature, os.getenv("CALCOM_WEBHOOK_SECRET")):
            raise HTTPException(status_code=401, detail="Invalid Signature")
        
        data = await request.json()
        payload = data.get('payload', {})
        attendees = payload.get('attendees', [])
        
        if not attendees:
            raise HTTPException(status_code=400, detail="No attendee data")

        # Extract values for Brevo
        attendee_email = attendees[0].get('email')
        attendee_name = attendees[0].get('name', 'Cal.com Lead')

        # 1. Save to Supabase (Capital L)
        supabase.table("Leads").insert({
            "name": attendee_name, 
            "email": attendee_email, 
            "source": "calendly",
            "sequence": "A", 
            "business": "Booked via Cal.com"
        }).execute()
        
        # 2. Add to Brevo List 7 (Sarmad's Request)
        add_to_brevo(attendee_email, attendee_name, 7)
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    try:
        supabase.table("Chat_sessions").insert({
            "email": body.email, "flow": body.flow, "messages": []
        }).execute()
        add_to_brevo(body.email, body.name, 6)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))