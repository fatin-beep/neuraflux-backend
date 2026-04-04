from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

# 1. Load Environment Variables
load_dotenv()

app = FastAPI()

# 2. Setup Supabase & Brevo Keys
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. Data Model for the Contact Form
class Lead(BaseModel):
    name: str
    email: EmailStr
    message: str

# --- NEW: THE HOME ROUTE ---
# This fixes the "Not Found" error when you open your Railway link
@app.get("/")
def read_root():
    return {
        "status": "online", 
        "message": "Neuraflux Backend is officially Live!",
        "version": "1.0.0"
    }

# 4. The Form Submission Route
@app.post("/submit-form")
async def create_lead(lead: Lead):
    try:
        # Save to Supabase
        data = {
            "name": lead.name,
            "email": lead.email,
            "message": lead.message
        }
        response = supabase.table("leads").insert(data).execute()

        # Send Email via Brevo
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = BREVO_API_KEY
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": "fatinbutt2@gmail.com", "name": "Fatin"}], # Change to your email
            reply_to={"email": lead.email, "name": lead.name},
            template_id=1, # Ensure you have a template set up in Brevo!
            params={"NAME": lead.name, "MESSAGE": lead.message}
        )
        
        api_instance.send_transac_email(send_smtp_email)

        return {"status": "success", "message": "Lead saved and email sent!"}

    except Exception as e:
        return {"status": "error", "message": str(e)}