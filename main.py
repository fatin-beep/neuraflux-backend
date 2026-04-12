import os
import sib_api_v3_sdk
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
app = FastAPI()

# --- MODELS ---
class ContactForm(BaseModel):
    name: str
    email: EmailStr
    business: str
    challenge: str

class ChatEmail(BaseModel):
    email: EmailStr
    name: str = "Chat Guest"
    flow: str = "B"

class AuditPayload(BaseModel):
    payload: dict

# --- CLIENTS ---
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = os.getenv("BREVO_API_KEY")
api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

# --- HELPERS ---
def add_to_brevo(email: str, first_name: str, list_id: int):
    try:
        create_contact = sib_api_v3_sdk.CreateContact(
            email=email,
            attributes={'FIRSTNAME': first_name},
            list_ids=[list_id],
            update_enabled=True
        )
        api_instance.create_contact(create_contact)
        print(f"Brevo Success: {email} added to list {list_id}")
    except Exception as e:
        print(f"Brevo Error: {e}")

# --- ENDPOINTS ---
@app.get('/')
def home():
    return {'message': 'NeuraFlux API Online', 'docs': '/docs'}

app.add_middleware(
    CORSMiddleware,
    allow_origins=['https://neuraflux.io', 'http://localhost:3000'],
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.post('/api/contact')
async def contact_form(body: ContactForm):
    try:
        supabase.table("Leads").insert({
            "name": body.name, "email": body.email, "business": body.business,
            "challenge": body.challenge, "source": "form", "sequence": "B"
        }).execute()
        add_to_brevo(body.email, body.name, 6)
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post('/api/audit-booked')
async def audit_booked(body: AuditPayload):
    try:
        data = body.payload
        attendees = data.get('attendees', [])
        if not attendees:
            return {"status": "error", "message": "No attendee data"}

        email = attendees[0].get('email')
        name = attendees[0].get('name', 'Cal.com Lead')

        # Save to Leads table and trigger Sequence A (List 7)
        supabase.table("Leads").insert({
            "name": name, "email": email, "source": "calendly", 
            "sequence": "A", "business": "Booked Audit"
        }).execute()

        add_to_brevo(email, name, 7)
        return {"status": "success"}
    except Exception as e:
        print(f"Crash Details: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    try:
        supabase.table("Chat_sessions").insert({
            "email": body.email, "flow": body.flow, "messages": []
        }).execute()
        add_to_brevo(body.email, body.name, 6)
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")