import os
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, validator
from dotenv import load_dotenv
from supabase import create_client, Client

# Brevo SDK
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException as BrevoApiException

# --- CONFIGURE LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- LOAD ENV ---
load_dotenv()

# --- ENVIRONMENT CONFIGURATION ---
class Config:
    """Centralized configuration with validation"""
    BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SELF_URL: str = os.getenv("SELF_URL", "http://localhost:8000")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Brevo List IDs
    BREVO_LIST_CONTACT: int = int(os.getenv("BREVO_LIST_CONTACT", "6"))      # Sequence B
    BREVO_LIST_AUDIT: int = int(os.getenv("BREVO_LIST_AUDIT", "7"))      # Sequence A
    
    # Sarmad's booking page
    SARMAD_BOOKING_PAGE: str = os.getenv("SARMAD_BOOKING_PAGE", "https://cal.com/neuraflux-iitdmq/30min")
    
    # CORS Origins
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:3000,https://neuraflux.io").split(",")

# --- VALIDATE REQUIRED ENV ---
REQUIRED_ENV = ["BREVO_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
missing_vars = [var for var in REQUIRED_ENV if not getattr(Config, var)]
if missing_vars:
    raise Exception(f"Missing required ENV variables: {', '.join(missing_vars)}")

# --- MODELS ---
class ContactForm(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="User's full name")
    email: EmailStr
    business: str = Field(..., min_length=1, max_length=200, description="Business name")
    challenge: str = Field(..., min_length=1, max_length=2000, description="Business challenge description")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()

class ChatEmail(BaseModel):
    email: EmailStr
    name: str = Field(default="Chat Guest", max_length=100)
    flow: str = Field(default="B", pattern="^[AB]$")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            return "Chat Guest"
        return v.strip()

class AuditPayload(BaseModel):
    payload: dict = Field(..., description="Cal.com webhook payload")

# --- CLIENTS ---
supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

# Brevo configuration
brevo_config = sib_api_v3_sdk.Configuration()
brevo_config.api_key['api-key'] = Config.BREVO_API_KEY
brevo_api_client = sib_api_v3_sdk.ApiClient(brevo_config)
contact_api = sib_api_v3_sdk.ContactsApi(brevo_api_client)

# --- HELPER FUNCTIONS ---
def get_first_name(full_name: str) -> str:
    """Safely extract first name from full name"""
    if not full_name:
        return "Guest"
    cleaned = full_name.strip()
    if not cleaned:
        return "Guest"
    return cleaned.split()[0]

async def add_to_brevo_async(email: str, first_name: str, list_id: int, attributes: Optional[dict] = None):
    """Async wrapper for Brevo contact creation."""
    try:
        attrs = attributes.copy() if attributes else {}
        attrs['FIRSTNAME'] = first_name

        contact = sib_api_v3_sdk.CreateContact(
            email=email,
            attributes=attrs,
            list_ids=[list_id],
            update_enabled=True
        )
        
        # CRITICAL FIX: Run sync Brevo SDK in thread pool
        await asyncio.to_thread(contact_api.create_contact, contact)
        logger.info(f"Contact added/updated: {email} to list {list_id}")
        
    except BrevoApiException as e:
        if e.status == 400 and "already exists" in str(e).lower():
            logger.info(f"Contact {email} already exists, attributes updated")
        else:
            logger.error(f"Brevo API error: {e}")
            raise Exception(f"Brevo API failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected Brevo error: {e}")
        raise Exception(f"Brevo operation failed: {e}")

# --- KEEP ALIVE LOGIC ---
async def keep_alive():
    """Ping our own server every 14 minutes to prevent Railway sleep"""
    await asyncio.sleep(60)
    
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{Config.SELF_URL}/api/health",
                    timeout=10
                )
                if response.status_code == 200:
                    logger.info('Keep-alive ping successful')
                else:
                    logger.warning(f'Keep-alive ping returned {response.status_code}')
        except Exception as e:
            logger.warning(f'Keep-alive ping failed (non-critical): {e}')
        
        await asyncio.sleep(840)  # 14 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info(f"Starting NeuraFlux API in {Config.ENVIRONMENT} mode")
    
    if Config.ENVIRONMENT == "production":
        asyncio.create_task(keep_alive())
        logger.info("Keep-alive task started")
    
    yield
    
    logger.info("Shutting down NeuraFlux API")

# --- APP INITIALIZATION ---
app = FastAPI(
    title="NeuraFlux API",
    description="API for NeuraFlux Agency Website",
    version="1.0.0",
    lifespan=lifespan
)

# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ERROR HANDLERS ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": "Internal server error"}
    )

# --- ROUTES ---
@app.get('/')
def home():
    return {
        'message': 'NeuraFlux API Online',
        'docs': '/docs',
        'health': '/api/health',
        'environment': Config.ENVIRONMENT
    }

@app.get('/api/health')
def health():
    return {
        'status': 'ok',
        'timestamp': asyncio.get_event_loop().time(),
        'environment': Config.ENVIRONMENT
    }

@app.post('/api/contact')
async def contact_form(body: ContactForm):
    """Handle contact form submissions."""
    try:
        result = await asyncio.to_thread(
            supabase.table("leads").insert({
                "name": body.name,
                "email": body.email,
                "business": body.business,
                "challenge": body.challenge,
                "source": "form",
                "sequence": "B",
                "created_at": "now()"
            }).execute
        )
        
        logger.info(f"Lead saved to Supabase: {body.email}")
        
        first_name = get_first_name(body.name)
        await add_to_brevo_async(
            email=str(body.email),
            first_name=first_name,
            list_id=Config.BREVO_LIST_CONTACT
        )
        
        return {
            "status": "success",
            "message": "Thank you! We'll be in touch soon."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contact form error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process your submission. Please try again."
        )

@app.post('/api/audit-booked')
async def audit_booked(body: AuditPayload):
    """Handle Cal.com booking webhook."""
    try:
        logger.info('Audit booking webhook received')
        data = body.payload
        attendees = data.get('attendees', [])

        if not attendees or not isinstance(attendees, list):
            return {'status': 'error', 'message': 'No attendee data'}

        email = attendees[0].get('email')
        name = attendees[0].get('name', 'Guest')

        if not email:
            return {'status': 'error', 'message': 'No email in payload'}

        start_time = data.get('startTime', '')
        booking_uid = data.get('uid', '')
        
        video_url = data.get('metadata', {}).get('videoCallUrl', '')
        if not video_url or "app.cal.com/video" in video_url:
            video_url = Config.SARMAD_BOOKING_PAGE

        if booking_uid:
            reschedule_url = f'https://cal.com/reschedule/{booking_uid}'
        else:
            reschedule_url = Config.SARMAD_BOOKING_PAGE

        first_name = get_first_name(name)

        await asyncio.to_thread(
            supabase.table('leads').insert({
                'name': name,
                'email': email,
                'source': 'calendly',
                'sequence': 'A',
                'business': 'Booked Audit',
                'created_at': 'now()'
            }).execute
        )
        logger.info(f"Audit lead saved: {email}")

        custom_attributes = {
            'CALENDAR_URL': video_url,
            'RESCHEDULE_URL': reschedule_url,
            'START_TIME': start_time
        }
        await add_to_brevo_async(
            email=email,
            first_name=first_name,
            list_id=Config.BREVO_LIST_AUDIT,
            attributes=custom_attributes
        )

        return {
            'status': 'success',
            'message': 'Audit booking processed'
        }
        
    except Exception as e:
        logger.error(f'Error in /api/audit-booked: {e}', exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to process booking'
        )

@app.post('/api/chat/email')
async def chat_email(body: ChatEmail):
    """Handle chat email capture."""
    try:
        await asyncio.to_thread(
            supabase.table("chat_sessions").insert({
                "email": body.email,
                "flow": body.flow,
                "messages": [],
                "created_at": "now()"
            }).execute
        )
        logger.info(f"Chat session saved: {body.email}")

        first_name = get_first_name(body.name)
        await add_to_brevo_async(
            email=str(body.email),
            first_name=first_name,
            list_id=Config.BREVO_LIST_CONTACT
        )

        return {
            "status": "success",
            "message": "Email saved successfully"
        }
        
    except Exception as e:
        logger.error(f"Chat email error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save email"
        )

# --- RUN (for local development) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))