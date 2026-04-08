import os
import requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
app = FastAPI()

# 1. Setup Environment Variables
BREVO_API_KEY = os.getenv('BREVO_API_KEY')
BREVO_URL = 'https://api.brevo.com/v3/contacts'
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- DATA MODELS ---
class LeadCapture(BaseModel):
    name: str        # Matches 'name' in screenshot
    email: str       # Matches 'email' in screenshot
    business: str    # Matches 'business' in screenshot
    challenge: str   # Matches 'challenge' in screenshot

class ChatSession(BaseModel):
    flow: str
    email: str
    messages: dict   # Matches {} json in your text description

# --- HEALTH CHECK ---
@app.get("/")
def read_root():
    return {"status": "online", "message": "Neuraflux Backend Synced!"}

# --- ENDPOINT 1: Website Form (Saves to 'Leads' table) ---
@app.post('/api/email-capture')
async def email_capture(body: LeadCapture):
    try:
        # 1. Insert into Hamza's 'Leads' table
        supabase.table("Leads").insert({
            "name": body.name,
            "email": body.email,
            "business": body.business,
            "challenge": body.challenge
        }).execute()

        # 2. Trigger Brevo Sequence B
        requests.post(BREVO_URL, json={
            'email': body.email,
            'attributes': {'FIRSTNAME': body.name, 'sequence': 'B'},
            'updateEnabled': True
        }, headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json'})

        return {'status': 'ok'}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- ENDPOINT 2: Chatbot (Saves to 'Chat_sessions' table) ---
@app.post('/api/chat/session')
async def save_chat(body: ChatSession):
    try:
        # 1. Insert into 'Chat_sessions' table
        supabase.table("Chat_sessions").insert({
            "flow": body.flow,
            "email": body.email,
            "messages": body.messages
        }).execute()

        # 2. Trigger Brevo if email is provided
        if body.email:
            requests.post(BREVO_URL, json={
                'email': body.email,
                'attributes': {'sequence': 'B'},
                'updateEnabled': True
            }, headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json'})

        return {'status': 'ok'}
    except Exception as e:
        return {"status": "error", "message": str(e)}