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
        raise Exception(f"❌ Missing ENV variable: {var}")

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


# ✅ USER EMAIL
def send_email(to_email: str, to_name: str):
    try:
        email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_email, "name": to_name}],
            sender={
                "email": "contact@neuraflux.io",
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
        print(f"✅ User email sent to {to_email}")
        return response

    except Exception as e:
        print(f"❌ Email Error: {e}")
        raise Exception(f"Email failed: {e}")


# ✅ ADMIN EMAIL (NEW)
def send_admin_email(name: str, email: str, business: str = "", challenge: str = ""):
    try:
        email_data = sib_api_v3_sdk.SendSmtpEmail(
            to=[{
                "email": "your@email.com",  # 🔥 CHANGE THIS
                "name": "Admin"
            }],
            sender={
                "email": "contact@neuraflux.io",
                "name": "NeuraFlux"
            },
            subject="🚨 New Lead Received",
            html_content=f"""
                <h2>New Lead Submitted</h2>
                <p><strong>Name:</strong> {name}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Business:</strong> {business}</p>
                <p><strong>Challenge:</strong> {challenge}</p>
            """
        )

        response = email_api.send_transac_email(email_data)
        print("✅ Admin email sent")
        return response

    except Exception as e:
        print(f"❌ Admin Email Error: {e}")


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


# ✅ CONTACT FORM
@app.post('/api/contact')
async def contact_form(body: ContactForm):
    try:
        print("📩 Contact API HIT")

        # Save to DB
        supabase.table("Leads").insert({
            "name": body.name,
            "email": body.email,
            "business": body.business,
            "challenge": body.challenge,
            "source": "form",
            "sequence": "B"
        }).execute()

        print("✅ Saved to Supabase")

        # Brevo
        add_to_brevo(body.email, body.name, 6)

        # Emails
        send_email(body.email, body.name)
        send_admin_email(body.name, body.email, body.business, body.challenge)

        return {"status": "success"}

    except Exception as e:
        print(f"🔥 ERROR in /api/contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ✅ AUDIT BOOKED
@app.post('/api/audit-booked')
async def audit_booked(body: AuditPayload):
    try:
        print("📅 Audit API HIT")

        data = body.payload
        attendees = data.get('attendees', [])

        if not attendees:
            return {"status": "error", "message": "No attendee data"}

        email = attendees[0].get('email')
        name = attendees[0].get('name', 'Audit Client')

        supabase.table("Leads").insert({
            "name": name,
            "email": email,
            "source": "audit",
            "sequence": "A",
            "business": "Booked Audit"
        }).execute()

        print("✅ Saved audit lead")

        add_to_brevo(email, name, 7)

        # Emails
        send_email(email, name)
        send_admin_email(name, email)

        return {"status": "success"}

    except Exception as e:
        print(f"🔥 ERROR in /api/audit-booked: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ✅ CHAT EMAIL
@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    try:
        print("💬 Chat API HIT")

        supabase.table("Chat_sessions").insert({
            "email": body.email,
            "flow": body.flow,
            "messages": []
        }).execute()

        print("✅ Chat saved")

        add_to_brevo(body.email, body.name, 6)

        # Emails
        send_email(body.email, body.name)
        send_admin_email(body.name, body.email)

        return {"status": "success"}

    except Exception as e:
        print(f"🔥 ERROR in /api/chat/email: {e}")
        raise HTTPException(status_code=500, detail=str(e))