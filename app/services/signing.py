"""One-time demo signature codes. Never SMS or qualified digital signatures."""
from datetime import timedelta
from hashlib import sha256
import hmac
import secrets
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.operations import SigningChallenge
from app.services.operations import utcnow,aware


def code_digest(code,id_,user_id,settings):
    key=settings.signing_code_secret.get_secret_value() or settings.db_password.get_secret_value()
    return hmac.new(key.encode(),f'delora-demo-sign:{id_}:{user_id}:{code}'.encode(),sha256).hexdigest()


async def issue_code(db,row,offer,user,settings):
    if not user.can_sign:raise HTTPException(403,'Нужно право подписи')
    if row.status!='offer_accepted' or offer.status!='accepted':raise HTTPException(409,'Сначала примите предложение')
    recent=await db.scalar(select(SigningChallenge).where(SigningChallenge.offer_id==offer.id,SigningChallenge.user_id==user.id)
                           .order_by(SigningChallenge.created_at.desc()).limit(1))
    if recent and (utcnow()-aware(recent.created_at)).total_seconds()<10:
        raise HTTPException(429,'Повторный код можно получить через 10 секунд')
    previous=list((await db.scalars(select(SigningChallenge).where(SigningChallenge.offer_id==offer.id,SigningChallenge.consumed_at.is_(None)))).all())
    for item in previous:item.consumed_at=utcnow()
    code=f'{secrets.randbelow(1000000):06d}';id_=uuid4();expires=utcnow()+timedelta(seconds=settings.signing_code_ttl_seconds)
    db.add(SigningChallenge(id=id_,offer_id=offer.id,user_id=user.id,code_hash=code_digest(code,id_,user.id,settings),attempts=0,expires_at=expires))
    return dict(challenge_id=id_,expires_at=expires,demo_code=code if settings.demo_auth_enabled and settings.demo_signing_code_visible else None)


async def verify_code(db,offer,user,challenge_id,code,settings):
    challenge=await db.scalar(select(SigningChallenge).where(SigningChallenge.id==challenge_id).with_for_update()) if challenge_id else None
    if not challenge or challenge.offer_id!=offer.id or challenge.user_id!=user.id:
        raise HTTPException(422,'Код не относится к этому предложению и подписанту')
    if challenge.consumed_at or aware(challenge.expires_at)<=utcnow() or challenge.attempts>=settings.signing_code_max_attempts:
        raise HTTPException(409,'Код истёк, использован или заблокирован')
    challenge.attempts+=1
    if not hmac.compare_digest(challenge.code_hash,code_digest(code or '',challenge.id,user.id,settings)):
        # Failed guesses must survive the HTTP exception/rollback boundary.
        await db.commit()
        raise HTTPException(422,'Неверный демонстрационный код')
    challenge.consumed_at=utcnow()
