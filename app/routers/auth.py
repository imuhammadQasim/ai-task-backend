# app/routers/auth.py
from jose import jwt, JWTError
from fastapi import APIRouter, Header, HTTPException, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from svix.webhooks import Webhook, WebhookVerificationError
from app.database import get_db
from app.config import settings
from app.models.user import User

router = APIRouter()

# JWKS_CLERK_KEY stores the raw base64 SPKI body (as copied from the Clerk
# dashboard) without PEM headers; python-jose requires the full PEM block.
_CLERK_PUBLIC_KEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n" + settings.JWKS_CLERK_KEY + "\n-----END PUBLIC KEY-----\n"
)

# Dependency to get current user from Bearer Token, verified locally via RS256
# against Clerk's public key (JWKS_CLERK_KEY) instead of calling Clerk's API.
async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            _CLERK_PUBLIC_KEY_PEM,
            algorithms=["RS256"],
            audience=None,
            options={"verify_aud": False},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed: sub not found"
        )

    # Just-in-time user provisioning: the Clerk user.created webhook can't reach
    # a local backend, so ensure an authenticated user always has a DB row to
    # satisfy foreign keys (e.g. tasks.user_id). The webhook still backfills the
    # real email later if/when it fires.
    result = await db.execute(select(User).where(User.id == user_id))
    if result.scalar_one_or_none() is None:
        db.add(User(
            id=user_id,
            clerk_id=user_id,
            email=f"{user_id}@noemail.clerk",
            plan_tier="free",
        ))
        await db.commit()

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
