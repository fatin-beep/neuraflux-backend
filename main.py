import os
import sib_api_v3_sdk

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from supabase import create_client, Client

# --- LOAD ENV ---
load_dotenv()

app = FastAPI()

# --- VALIDATE ENV ---
REQUIRED_ENV = ["BREVO_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]

for var in REQUIRED_ENV:
    if not os.getenv(var):
        raise Exception(f"Missing ENV variable: {var}")

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
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# Brevo config
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = os.getenv("BREVO_API_KEY")

contact_api = sib_api_v3_sdk.ContactsApi(
    sib_api_v3_sdk.ApiClient(configuration)
)

# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=['https://neuraflux.io', 'http://localhost:3000'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# --- HELPER ---

def add_to_brevo(email: str, first_name: str, list_id: int, attributes: dict = None):
    """
    Adds a contact to a Brevo list.
    Attributes support dynamic fields like CALENDAR_URL and RESCHEDULE_URL.
    """
    try:
        if attributes is None:
            attributes = {}
        
        attributes['FIRSTNAME'] = first_name

        contact = sib_api_v3_sdk.CreateContact(
            email=email,
            attributes=attributes,
            list_ids=[list_id],
            update_enabled=True
        )
        contact_api.create_contact(contact)
        print(f"Contact added: {email} to list {list_id}")
    except Exception as e:
        print(f"Brevo error: {e}")
        raise Exception(f"Brevo failed: {e}")


# --- ROUTES ---

@app.get('/')
def home():
    return {'message': 'NeuraFlux API Online', 'docs': '/docs'}


@app.post('/api/contact')
async def contact_form(body: ContactForm):
    try:
        supabase.table("Leads").insert({
            "name": body.name,
            "email": body.email,
            "business": body.business,
            "challenge": body.challenge,
            "source": "form",
            "sequence": "B"
        }).execute()

        add_to_brevo(body.email, body.name.split()[0], 6)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post('/api/audit-booked')
async def audit_booked(body: AuditPayload):
    """
    Extracts booking details from Cal.com and passes them to Brevo.
    Ensures the 'Add to Calendar' button leads to a real booking page.
    """
    try:
        print('Audit booking webhook received')
        data = body.payload
        attendees = data.get('attendees', [])

        if not attendees:
            return {'status': 'error', 'message': 'No attendee data'}

        email = attendees[0].get('email')
        name = attendees[0].get('name', 'Guest')
        first_name = name.split()[0]

        if not email:
            return {'status': 'error', 'message': 'No email in payload'}

        # --- SARMAD'S BOOKING PAGE ---
        SARMAD_BOOKING_PAGE = "https://cal.com/neuraflux-iitdmq/30min"

        # Extract details from Cal.com
        start_time = data.get('startTime', '')
        booking_uid = data.get('uid', '')
        
        # Check for specific video link; use booking page as fallback
        video_url = data.get('metadata', {}).get('videoCallUrl', '')
        if not video_url or "app.cal.com/video" in video_url:
            video_url = SARMAD_BOOKING_PAGE

        # [span_5](start_span)Build reschedule URL[span_5](end_span)
        reschedule_url = f'https://cal.com/reschedule/{booking_uid}'

        # 1. [span_6](start_span)Save to Supabase[span_6](end_span)
        supabase.table('Leads').insert({
            'name': name,
            'email': email,
            'source': 'calendly',
            'sequence': 'A',
            'business': 'Booked Audit'
        }).execute()

        # 2. [span_7](start_span)Add to Brevo with button attributes[span_7](end_span)
        custom_attributes = {
            'CALENDAR_URL': video_url,
            'RESCHEDULE_URL': reschedule_url,
            'START_TIME': start_time
        }
        
        add_to_brevo(email, first_name, 7, custom_attributes)

        return {'status': 'success'}

    except Exception as e:
        print(f'Error in /api/audit-booked: {e}')
        raise HTTPException(status_code=500, detail='Something went wrong')


@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    try:
        supabase.table("Chat_sessions").insert({
            "email": body.email,
            "flow": body.flow,
            "messages": []
        }).execute()

        add_to_brevo(body.email, body.name.split()[0], 6)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")