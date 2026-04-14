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

def add_to_brevo(email: str, first_name: str, list_id: int):
    """
    Adds a contact to a Brevo list.
    List ID 7 = Booked Audit  → triggers Sequence A (NF-A1, NF-A2)
    List ID 6 = Email Only    → triggers Sequence B (NF-B1 through NF-B5)
    Brevo automation handles all email sending automatically.
    Do NOT send emails manually — the automation does it.
    """
    try:
        contact = sib_api_v3_sdk.CreateContact(
            email=email,
            attributes={'FIRSTNAME': first_name},
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


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.post('/api/contact')
async def contact_form(body: ContactForm):
    """
    Triggered when visitor submits the contact form on the website.
    Saves to Supabase and adds to Brevo Email Only list (ID 6).
    Brevo automatically sends Sequence B emails.
    """
    try:
        print("Contact form received")

        # Save to Supabase
        supabase.table("Leads").insert({
            "name": body.name,
            "email": body.email,
            "business": body.business,
            "challenge": body.challenge,
            "source": "form",
            "sequence": "B"
        }).execute()

        print("Saved to Supabase")

        # Add to Brevo Email Only list — triggers Sequence B automatically
        add_to_brevo(body.email, body.name.split()[0], 6)

        return {"status": "success"}

    except Exception as e:
        print(f"Error in /api/contact: {e}")
        raise HTTPException(status_code=500, detail="Something went wrong")


@app.post('/api/audit-booked')
async def audit_booked(body: AuditPayload):
    """
    Triggered by Cal.com webhook when someone books a Free AI Growth Audit.
    Saves to Supabase and adds to Brevo Booked Audit list (ID 7).
    Passes calendar URL, reschedule URL, and start time as contact attributes.
    Brevo automation sends NF-A1 email automatically using these attributes.
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

        # Extract booking details from Cal.com payload
        start_time = data.get('startTime', '')
        booking_uid = data.get('uid', '')
        video_url = data.get('metadata', {}).get('videoCallUrl', '')
        
        if not video_url:
            video_url = data.get('location', 'https://app.cal.com/video')

        # Build reschedule URL from booking UID
        reschedule_url = f'https://cal.com/reschedule/{booking_uid}'

        # Save to Supabase
        supabase.table('Leads').insert({
            'name': name,
            'email': email,
            'source': 'calendly',
            'sequence': 'A',
            'business': 'Booked Audit'
        }).execute()

        print(f'Saved audit lead: {email}')

        # Add to Brevo Booked Audit list with all attributes
        # This triggers Sequence A automatically
        # Brevo uses these attributes to fill the email template buttons
        try:
            contact = sib_api_v3_sdk.CreateContact(
                email=email,
                attributes={
                    'FIRSTNAME': first_name,
                    'CALENDAR_URL': video_url,
                    'RESCHEDULE_URL': reschedule_url,
                    'START_TIME': start_time
                },
                list_ids=[7],
                update_enabled=True
            )
            contact_api.create_contact(contact)
            print(f'Contact added to Brevo list 7: {email}')
        except Exception as e:
            print(f'Brevo error: {e}')
            raise Exception(f'Brevo failed: {e}')

        return {'status': 'success'}

    except Exception as e:
        print(f'Error in /api/audit-booked: {e}')
        raise HTTPException(status_code=500, detail='Something went wrong')


@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    """
    Triggered when the chatbot captures a visitor's email.
    Saves to Supabase and adds to Brevo Email Only list (ID 6).
    Brevo automatically sends Sequence B emails.
    """
    try:
        print("Chatbot email capture received")

        # Save to Supabase
        supabase.table("Chat_sessions").insert({
            "email": body.email,
            "flow": body.flow,
            "messages": []
        }).execute()

        print(f"Chat session saved: {body.email}")

        # Add to Brevo Email Only list — triggers Sequence B automatically
        add_to_brevo(body.email, body.name.split()[0], 6)

        return {"status": "success"}

    except Exception as e:
        print(f"Error in /api/chat/email: {e}")
        raise HTTPException(status_code=500, detail="Something went wrong")