import os
import sib_api_v3_sdk

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from supabase import create_client, Client

# Load env
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

email_api = sib_api_v3_sdk.TransactionalEmailsApi(
    sib_api_v3_sdk.ApiClient(configuration)
)

# --- HELPERS ---

def add_to_brevo(email: str, first_name: str, list_id: int):
    try:
        contact = sib_api_v3_sdk.CreateContact(
            email=email,
            attributes={'FIRSTNAME': first_name},
            list_ids=[list_id],
            update_enabled=True
        )
        contact_api.create_contact(contact)
        print(f"✅ Contact added: {email} → list {list_id}")
    except Exception as e:
        print(f"❌ Brevo Contact Error: {e}")


def send_email(to_email: str, to_name: str):
    try:
        email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_email, "name": to_name}],
            sender={
                "email": "contact@neuraflux.io",  # MUST be verified in Brevo
                "name": "NeuraFlux"
            },
            subject="Your Request is Confirmed 🚀",
            html_content=f"""
                <h2>Hi {to_name},</h2>
                <p>Thanks for reaching out! We've received your request.</p>
                <p>Our team will contact you shortly.</p>
                <br>
                <p>— NeuraFlux Team</p>
            """
        )

        response = email_api.send_transac_email(email)
        print(f"✅ Email sent to {to_email}")
        return response

    except Exception as e:
        print(f"❌ Email Error: {e}")


# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=['https://neuraflux.io', 'http://localhost:3000'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# --- ROUTES ---

@app.get('/')
def home():
    return {'message': 'NeuraFlux API Online', 'docs': '/docs'}


@app.post('/api/contact')
async def contact_form(body: ContactForm):
    try:
        # Save to DB
        supabase.table("Leads").insert({
            "name": body.name,
            "email": body.email,
            "business": body.business,
            "challenge": body.challenge,
            "source": "form",
            "sequence": "B"
        }).execute()

        # Add to Brevo list
        add_to_brevo(body.email, body.name, 6)

        # ✅ SEND EMAIL
        send_email(body.email, body.name)

        return {"status": "success"}

    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post('/api/audit-booked')
async def audit_booked(body: AuditPayload):
    try:
        data = body.payload
        attendees = data.get('attendees', [])

        if not attendees:
            return {"status": "error", "message": "No attendee data"}

        email = attendees[0].get('email')
        name = attendees[0].get('name', 'Audit Client')

        # Save to DB
        supabase.table("Leads").insert({
            "name": name,
            "email": email,
            "source": "audit",
            "sequence": "A",
            "business": "Booked Audit"
        }).execute()

        # Add to Brevo
        add_to_brevo(email, name, 7)

        # ✅ SEND EMAIL
        send_email(email, name)

        return {"status": "success"}

    except Exception as e:
        print(f"❌ Crash: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    try:
        # Save session
        supabase.table("Chat_sessions").insert({
            "email": body.email,
            "flow": body.flow,
            "messages": []
        }).execute()

        # Add to Brevo
        add_to_brevo(body.email, body.name, 6)

        # ✅ SEND EMAIL
        send_email(body.email, body.name)

        return {"status": "success"}

    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")