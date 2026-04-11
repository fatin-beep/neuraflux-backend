import os
import hmac
import hashlib
import sib_api_v3_sdk
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
brevo_contacts_api = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

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

def add_to_brevo(email: str, first_name: str, list_id: int):
    try:
        contact = sib_api_v3_sdk.CreateContact(
            email=email,
            attributes={'FIRSTNAME': first_name},
            list_ids=[list_id],
            update_enabled=True
        )
        brevo_contacts_api.create_contact(contact)
    except Exception as e:
        print(f"Brevo Error: {e}")

@app.get('/api/health')
def health():
    return {'status': 'ok'}

# 1. HAMZA'S ENDPOINT (Website Form)
@app.post('/api/contact')
async def contact_form(body: ContactForm):
    try:
        supabase.table("Leads").insert({
            "name": body.name, "email": body.email, "business": body.business,
            "challenge": body.challenge, "source": "form", "sequence": "B"
        }).execute()
        add_to_brevo(body.email, body.name, int(os.getenv('SEQUENCE_B_ID', 6)))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. SARMAD'S ENDPOINT (Cal.com Booking)
@app.post('/api/audit-booked')
async def audit_booked(request: Request):
    try:
        body_bytes = await request.body()
        signature = request.headers.get("X-Cal-Signature-256")
        if not verify_cal_signature(body_bytes, signature, os.getenv("CALCOM_WEBHOOK_SECRET")):
            raise HTTPException(status_code=401, detail="Invalid Signature")
        
        data = await request.json()
        payload = data.get('payload', {})
        attendees = payload.get('attendees', [])
        email = attendees[0].get('email')
        name = attendees[0].get('name', 'Cal.com Lead')

        supabase.table("Leads").insert({
            "name": name, "email": email, "source": "calendly",
            "sequence": "A", "business": "Booked via Cal.com"
        }).execute()
        
        add_to_brevo(email, name, int(os.getenv('SEQUENCE_A_ID', 7)))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. ABDULLAH'S ENDPOINT (Chatbot)
@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    try:
        supabase.table("Chat_sessions").insert({"email": body.email, "flow": body.flow}).execute()
        add_to_brevo(body.email, body.name, int(os.getenv('SEQUENCE_B_ID', 6)))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))