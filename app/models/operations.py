"""Persistent operations: jobs, collaboration, model provenance and loan servicing."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class PipelineJob(Base):
    __tablename__='pipeline_jobs'
    __table_args__=(UniqueConstraint('application_id','submission',name='uq_job_submission'),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    application_id:Mapped[UUID]=mapped_column(ForeignKey('loan_applications.id'),index=True)
    submission:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(16),default='PENDING',index=True)
    stage:Mapped[int]=mapped_column(Integer,default=0)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    lease_token:Mapped[str|None]=mapped_column(String(36))
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    run_after:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    last_error:Mapped[str|None]=mapped_column(Text)
    snapshot:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))


class WorkerHeartbeat(Base):
    __tablename__='worker_heartbeats'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    seen_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))


class SourceSetting(Base):
    __tablename__='source_settings'
    name:Mapped[str]=mapped_column(String(24),primary_key=True)
    mode:Mapped[str]=mapped_column(String(24),default='success')
    failures:Mapped[int]=mapped_column(Integer,default=0)
    open_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    updated_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class PolicyVersion(Base):
    __tablename__='policy_versions'
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    definition:Mapped[dict]=mapped_column(JSON)
    created_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class SystemSetting(Base):
    __tablename__='system_settings'
    key:Mapped[str]=mapped_column(String(64),primary_key=True)
    value:Mapped[dict]=mapped_column(JSON)


class AdminAudit(Base):
    __tablename__='admin_audit'
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(64))
    target:Mapped[str]=mapped_column(String(128))
    details:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class FinancialProfile(Base):
    __tablename__='financial_profiles'
    business_id:Mapped[int]=mapped_column(ForeignKey('businesses.id'),primary_key=True)
    kind:Mapped[str]=mapped_column(String(24))
    features:Mapped[dict]=mapped_column(JSON)
    provenance:Mapped[dict]=mapped_column(JSON)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class ModelPrediction(Base):
    __tablename__='model_predictions'
    __table_args__=(UniqueConstraint('application_id','submission',name='uq_prediction_submission'),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    application_id:Mapped[UUID]=mapped_column(ForeignKey('loan_applications.id'),index=True)
    submission:Mapped[int]=mapped_column(Integer)
    model_sha256:Mapped[str|None]=mapped_column(String(64))
    features:Mapped[dict]=mapped_column(JSON)
    provenance:Mapped[dict]=mapped_column(JSON)
    result:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class ApplicationTask(Base):
    __tablename__='application_tasks'
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    application_id:Mapped[UUID]=mapped_column(ForeignKey('loan_applications.id'),index=True)
    kind:Mapped[str]=mapped_column(String(16))
    title:Mapped[str]=mapped_column(String(255))
    description:Mapped[str]=mapped_column(Text,default='')
    required:Mapped[bool]=mapped_column(Boolean,default=True)
    document_type:Mapped[str|None]=mapped_column(String(20))
    status:Mapped[str]=mapped_column(String(16),default='OPEN')
    created_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'))
    due_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    answer:Mapped[str|None]=mapped_column(Text)
    document_id:Mapped[UUID|None]=mapped_column(ForeignKey('documents.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))


class ApplicationMessage(Base):
    __tablename__='application_messages'
    __table_args__=(UniqueConstraint('author_id','request_id',name='uq_message_request'),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    application_id:Mapped[UUID]=mapped_column(ForeignKey('loan_applications.id'),index=True)
    author_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    author_role:Mapped[str]=mapped_column(String(24))
    request_id:Mapped[UUID]=mapped_column(Uuid)
    text:Mapped[str]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class MessageRead(Base):
    __tablename__='message_reads'
    application_id:Mapped[UUID]=mapped_column(ForeignKey('loan_applications.id'),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),primary_key=True)
    read_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__='notifications'
    __table_args__=(UniqueConstraint('user_id','event_key',name='uq_notification_event'),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    application_id:Mapped[UUID|None]=mapped_column(ForeignKey('loan_applications.id'))
    event_key:Mapped[str]=mapped_column(String(160))
    kind:Mapped[str]=mapped_column(String(24))
    text:Mapped[str]=mapped_column(String(700))
    read:Mapped[bool]=mapped_column(Boolean,default=False)
    archived:Mapped[bool]=mapped_column(Boolean,default=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class DecisionRecord(Base):
    __tablename__='decision_records'
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    application_id:Mapped[UUID]=mapped_column(ForeignKey('loan_applications.id'),index=True)
    actor_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'))
    rules_version:Mapped[int]=mapped_column(Integer)
    action:Mapped[str]=mapped_column(String(24))
    reason:Mapped[str]=mapped_column(Text)
    terms:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class SigningChallenge(Base):
    __tablename__='signing_challenges'
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    offer_id:Mapped[UUID]=mapped_column(ForeignKey('credit_offers.id'),index=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    code_hash:Mapped[str]=mapped_column(String(64))
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    consumed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class LoanAccount(Base):
    __tablename__='loan_accounts'
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    application_id:Mapped[UUID]=mapped_column(ForeignKey('loan_applications.id'),unique=True)
    offer_id:Mapped[UUID]=mapped_column(ForeignKey('credit_offers.id'),unique=True)
    business_id:Mapped[int]=mapped_column(ForeignKey('businesses.id'),index=True)
    contract_number:Mapped[str]=mapped_column(String(64),unique=True)
    product_id:Mapped[str]=mapped_column(String(40))
    amount:Mapped[int]=mapped_column(Integer)
    months:Mapped[int]=mapped_column(Integer)
    annual_rate:Mapped[Decimal]=mapped_column(Numeric(5,2))
    schedule:Mapped[list]=mapped_column(JSON)
    issued_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class TeamInvitation(Base):
    __tablename__='team_invitations'
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    business_id:Mapped[int]=mapped_column(ForeignKey('businesses.id'))
    invited_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    email:Mapped[str]=mapped_column(String(255))
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    used_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))


class StreamLease(Base):
    __tablename__='stream_leases'
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
