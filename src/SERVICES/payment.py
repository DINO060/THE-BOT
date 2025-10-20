 # ==================== src/services/payment.py ====================
"""Payment processing service"""

import stripe
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from src.core.config import settings
from src.core.database import get_db, User, Transaction


class PaymentService:
    """Handle payment processing"""
    
    def __init__(self):
        if settings.stripe_api_key:
            stripe.api_key = settings.stripe_api_key
        self.webhook_secret = settings.stripe_webhook_secret
    
    async def create_checkout_session(
        self,
        user_id: int,
        plan: str = "premium_monthly"
    ) -> Optional[str]:
        """Create Stripe checkout session"""
        
        # Define plans
        plans = {
            "premium_monthly": {
                "price": "price_xxx",  # Stripe price ID
                "mode": "subscription"
            },
            "premium_yearly": {
                "price": "price_yyy",
                "mode": "subscription"
            },
            "one_time_boost": {
                "price": "price_zzz",
                "mode": "payment"
            }
        }
        
        if plan not in plans:
            return None
        
        plan_config = plans[plan]
        
        try:
            # Get user
            async with get_db() as db:
                user = await db.query(User).filter(
                    User.telegram_id == user_id
                ).first()
                
                if not user:
                    return None
                
                # Create or get customer
                if not user.stripe_customer_id:
                    customer = stripe.Customer.create(
                        metadata={"telegram_id": str(user_id)}
                    )
                    user.stripe_customer_id = customer.id
                    await db.commit()
            
            # Create checkout session
            session = stripe.checkout.Session.create(
                customer=user.stripe_customer_id,
                payment_method_types=["card"],
                line_items=[{
                    "price": plan_config["price"],
                    "quantity": 1
                }],
                mode=plan_config["mode"],
                success_url=f"https://t.me/{settings.bot_username}?start=payment_success",
                cancel_url=f"https://t.me/{settings.bot_username}?start=payment_cancel",
                metadata={
                    "user_id": str(user_id),
                    "plan": plan
                }
            )
            
            return session.url
            
        except stripe.error.StripeError as e:
            logging.error(f"Stripe error: {e}")
            return None
    
    async def handle_webhook(self, payload: bytes, sig_header: str) -> bool:
        """Handle Stripe webhook"""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
        except ValueError:
            return False
        except stripe.error.SignatureVerificationError:
            return False
        
        # Handle different event types
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            await self._fulfill_order(session)
        
        elif event["type"] == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            await self._cancel_subscription(subscription)
        
        return True
    
    async def _fulfill_order(self, session: Dict[str, Any]):
        """Fulfill order after successful payment"""
        user_id = int(session["metadata"]["user_id"])
        plan = session["metadata"]["plan"]
        
        async with get_db() as db:
            user = await db.query(User).filter(
                User.telegram_id == user_id
            ).first()
            
            if user:
                # Update user to premium
                user.is_premium = True
                
                if "monthly" in plan:
                    user.premium_until = datetime.utcnow() + timedelta(days=30)
                elif "yearly" in plan:
                    user.premium_until = datetime.utcnow() + timedelta(days=365)
                
                # Record transaction
                transaction = Transaction(
                    user_id=user.id,
                    transaction_id=session["id"],
                    payment_method="stripe",
                    amount=session["amount_total"] / 100,
                    currency=session["currency"],
                    status="completed",
                    stripe_payment_intent_id=session["payment_intent"],
                    metadata={"plan": plan}
                )
                db.add(transaction)
                
                await db.commit()
    
    async def _cancel_subscription(self, subscription: Dict[str, Any]):
        """Handle subscription cancellation"""
        customer_id = subscription["customer"]
        
        async with get_db() as db:
            user = await db.query(User).filter(
                User.stripe_customer_id == customer_id
            ).first()
            
            if user:
                user.is_premium = False
                user.premium_until = None
                await db.commit()