"""Idempotent offer-expiry notifications, shared safely by worker replicas."""
from datetime import timedelta
from sqlalchemy import select
from app.models.pipeline import CreditOffer
from app.models.loan_application import LoanApplication
from app.services.operations import notify,utcnow,aware


async def maintain(factory):
    async with factory() as db:
        offers=(await db.scalars(select(CreditOffer).where(CreditOffer.status=='offered',CreditOffer.expires_at<=utcnow()+timedelta(days=1)).limit(100))).all()
        for offer in offers:
            row=await db.get(LoanApplication,offer.application_id)
            expired=aware(offer.expires_at)<=utcnow()
            await notify(db,row,('offer-expired:' if expired else 'offer-expiring:')+str(offer.id),
                         'offer_expiry','Срок предложения истёк' if expired else 'Предложение скоро истекает',bank=False)
        await db.commit()
    # Add a schedule for historical demo issuances without rewriting their terms.
    from app.models.operations import LoanAccount
    from app.models.pipeline import DemoDisbursement
    from app.services.loans import new_loan
    async with factory() as db:
        rows=(await db.scalars(select(LoanApplication).join(DemoDisbursement,DemoDisbursement.application_id==LoanApplication.id)
              .outerjoin(LoanAccount,LoanAccount.application_id==LoanApplication.id).where(LoanAccount.id.is_(None))
              .with_for_update(of=LoanApplication,skip_locked=True).limit(20))).all()
        for row in rows:
            issuance=await db.scalar(select(DemoDisbursement).where(DemoDisbursement.application_id==row.id))
            offer=await db.get(CreditOffer,issuance.offer_id)
            if row.business_id and offer:db.add(new_loan(row,offer,issuance.created_at))
        await db.commit()
