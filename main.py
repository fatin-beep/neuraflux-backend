import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
app = FastAPI()

# Allow Browser Testing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connections
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# Brevo Configuration
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = os.environ.get("BREVO_API_KEY")
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

class LeadSchema(BaseModel):
    name: str
    email: str
    business: str
    challenge: str

def send_welcome_email(user_email, user_name):
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": user_email, "name": user_name}],
        sender={"email": "sarmad@neuraflux.io", "name": "Sarmad from NeuraFlux"},
        subject="We received your inquiry!",
        html_content=f"<html><body><h1>Hi {user_name}!</h1><p>Thanks for reaching out to NeuraFlux. We are reviewing your challenge and will get back to you shortly.</p></body></html>"
    )
    try:
        api_instance.send_trans_email(send_smtp_email)
        return True
    except ApiException as e:
        print(f"Email Error: {e}")
        return False

@app.post("/api/contact")
async def create_lead(lead: LeadSchema):
    data = {"name": lead.name, "email": lead.email, "business": lead.business, "challenge": lead.challenge}
    
    try:
        # 1. Save to Database
        supabase.table("leads").insert(data).execute()
        
        # 2. Send Welcome Email
        send_welcome_email(lead.email, lead.name)
        
        return {"status": "success", "message": "Lead saved and Email sent!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}