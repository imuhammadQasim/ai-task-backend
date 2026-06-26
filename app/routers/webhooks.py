# app/routers/webhooks.py
import stripe
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.config import settings
from app.models.user import User

router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
        
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        customer_id = data_object.get("customer")
        if customer_id:
            query = select(User).where(User.stripe_id == customer_id)
            # What if user.stripe_id isn't stored yet? We can also lookup/update via subscription.customer
            # Stripe customer might be matched via user ID in metadata or direct stripe_id.
            # "set user plan_tier='paid' by matching stripe customer ID"
            result = await db.execute(query)
            db_user = result.scalar_one_or_none()
            if db_user:
                db_user.plan_tier = "paid"
                await db.commit()
            else:
                # Attempt to lookup user by email or metadata if client stored user metadata in Stripe
                # Let's check metadata just in case
                metadata = data_object.get("metadata", {})
                user_id = metadata.get("user_id") or data_object.get("client_reference_id")
                if user_id:
                    query = select(User).where(User.id == user_id)
                    result = await db.execute(query)
                    db_user = result.scalar_one_or_none()
                    if db_user:
                        db_user.stripe_id = customer_id
                        db_user.plan_tier = "paid"
                        await db.commit()

    elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
        customer_id = data_object.get("customer")
        if customer_id:
            query = select(User).where(User.stripe_id == customer_id)
            result = await db.execute(query)
            db_user = result.scalar_one_or_none()
            if db_user:
                db_user.plan_tier = "free"
                await db.commit()

    return {"status": "ok"}
