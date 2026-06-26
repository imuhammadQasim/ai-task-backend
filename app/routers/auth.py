# app/routers/auth.py
import httpx
from fastapi import APIRouter, Header, HTTPException, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from svix.webhooks import Webhook, WebhookVerificationError
from app.database import get_db
from app.config import settings
from app.models.user import User

router = APIRouter()

# Dependency to get current user from Bearer Token verified against Clerk
async def get_current_user(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ")[1]
    
    # We call the Clerk verify endpoint to verify the Bearer token
    # https://api.clerk.com/v1/tokens/verify
    # Note: clerk API requests require authorization using Clerk API Secret, but
    # here the instruction says: "Use httpx to call https://api.clerk.com/v1/tokens/verify with the token as Bearer."
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.clerk.com/v1/tokens/verify",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Clerk verification request failed: {str(e)}"
            )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        data = response.json()
        user_id = data.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed: sub not found"
            )
        return user_id

@router.post("/clerk-webhook")
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    headers = request.headers
    payload = await request.body()
    
    svix_id = headers.get("svix-id")
    svix_signature = headers.get("svix-signature")
    svix_timestamp = headers.get("svix-timestamp")
    
    if not svix_id or not svix_signature or not svix_timestamp:
        raise HTTPException(status_code=400, detail="Missing Svix headers")
        
    wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
    try:
        msg = wh.verify(payload, {
            "svix-id": svix_id,
            "svix-signature": svix_signature,
            "svix-timestamp": svix_timestamp
        })
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = msg.get("type")
    event_data = msg.get("data", {})
    
    if event_type == "user.created":
        user_id = event_data.get("id")
        email_addresses = event_data.get("email_addresses", [])
        email = email_addresses[0].get("email_address") if email_addresses else None
        if not email:
            email = f"{user_id}@noemail.clerk"
            
        # Upsert user row
        query = select(User).where(User.id == user_id)
        result = await db.execute(query)
        db_user = result.scalar_one_or_none()
        if not db_user:
            db_user = User(
                id=user_id,
                clerk_id=user_id,
                email=email,
                plan_tier="free"
            )
            db.add(db_user)
        else:
            db_user.email = email
            db_user.clerk_id = user_id
        await db.commit()
        
    elif event_type == "user.deleted":
        user_id = event_data.get("id")
        query = select(User).where(User.clerk_id == user_id)
        result = await db.execute(query)
        db_user = result.scalar_one_or_none()
        if db_user:
            await db.delete(db_user)
            await db.commit()
            
    return {"status": "ok"}
