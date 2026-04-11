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

# Health Check
@app.get('/api/health')
def health():
    return {'status': 'ok'}

# [span_1](start_span)CORS Configuration[span_1](end_span)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['https://neuraflux.io', 'http://localhost:3000'],
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)

# [span_2](start_span)Clients Initialization[span_2](end_span)
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = os.getenv("BREVO_API_KEY")
api_instance = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))

# [span_3](start_span)Data Models[span_3](end_span)
class ContactForm(BaseModel):
    name: str
    email: EmailStr
    business: str
    challenge: str

class ChatEmail(BaseModel):
    email: EmailStr
    name: str = "Chat Guest"
    flow: str = "B"

# [span_4](start_span)Helper for Brevo[span_4](end_span)
def add_to_brevo(email: str, first_name: str, list_id: int):
    try:
        create_contact = sib_api_v3_sdk.CreateContact(
            email=email,
            attributes={'FIRSTNAME': first_name},
            list_ids=[list_id],
            update_enabled=True
        )
        api_instance.create_contact(create_contact)
    except ApiException as e:
        print(f"Brevo API Error: {e}")

# Endpoints

@app.post('/api/contact')
async def contact_form(body: ContactForm):
    try:
        # [span_5](start_span)Saving to table: Leads[span_5](end_span)
        supabase.table("Leads").insert({
            "name": body.name, "email": body.email, "business": body.business,
            "challenge": body.challenge, "source": "form", "sequence": "B"
        }).execute()
        add_to_brevo(body.email, body.name, 6)
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post('/api/audit-booked')
async def audit_booked(request: Request):
    try:
        data = await request.json()
        payload = data.get('payload', {})
        attendees = payload.get('attendees', [])
        
        if not attendees:
            raise HTTPException(status_code=400, detail="No attendee data")

        attendee_email = attendees[0].get('email')
        attendee_name = attendees[0].get('name', 'Cal.com Lead')

        # [span_6](start_span)Saving to table: Leads[span_6](end_span)
        supabase.table("Leads").insert({
            "name": attendee_name, "email": attendee_email, 
            "source": 'calendly', "sequence": 'A',
            "business": "Booked via Cal.com"
        }).execute()
        
        add_to_brevo(attendee_email, attendee_name, 7)
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    try:
        # [span_7](start_span)Saving to table: Chat_sessions[span_7](end_span)
        supabase.table("Chat_sessions").insert({
            "email": body.email, "flow": body.flow, "messages": []
        }).execute()
        add_to_brevo(body.email, body.name, 6)
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")