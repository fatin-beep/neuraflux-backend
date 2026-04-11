import os
import hmac
import hashlib
import sib_api_v3_sdk
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from supabase import create_client, Client
from sib_api_v3_sdk.rest import ApiException

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'], # Temporarily allow all for testing
    allow_methods=['*'],
    allow_headers=['*'],
)

# Initialize clients inside a try block to catch connection errors
try:
    supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = os.getenv("BREVO_API_KEY")
    brevo_contacts_api = sib_api_v3_sdk.ContactsApi(sib_api_v3_sdk.ApiClient(configuration))
except Exception as e:
    print(f"Initialization Error: {e}")

class ContactForm(BaseModel):
    name: str
    email: EmailStr
    business: str
    challenge: str

class ChatEmail(BaseModel):
    email: EmailStr
    name: str = "Chat User"
    flow: str = "B"

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

@app.post('/api/contact')
async def contact_form(body: ContactForm):
    try:
        # Saving to Supabase
        supabase.table("leads").insert({
            "name": body.name,
            "email": body.email,
            "business": body.business,
            "challenge": body.challenge,
            "source": "form",
            "sequence": "B"
        }).execute()
        
        # Triggering Brevo
        add_to_brevo(body.email, body.name, int(os.getenv('SEQUENCE_B_ID', 6)))
        return {"status": "success"}
    except Exception as e:
        # This will now show the REAL error in Swagger
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    try:
        supabase.table("chat_sessions").insert({
            "email": body.email,
            "flow": body.flow
        }).execute()
        
        add_to_brevo(body.email, body.name, int(os.getenv('SEQUENCE_B_ID', 6)))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))