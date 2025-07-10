"""SQLAlchemy models for EZ Scheduler"""

from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from .database import Base


class Conversation(Base):
    """Conversation model for storing user interactions"""
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False)
    status = Column(String, default="active")  # active, completed, archived
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    messages = relationship("Message", back_populates="conversation")
    signup_forms = relationship("SignupForm", back_populates="conversation")


class Message(Base):
    """Message model for storing conversation messages"""
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    role = Column(String, nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    message_metadata = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")


class SignupForm(Base):
    """Signup form model"""
    __tablename__ = "signup_forms"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    title = Column(String, nullable=False)
    event_date = Column(String, nullable=False)  # Will be properly typed later
    location = Column(String, nullable=False)
    description = Column(Text)
    url_slug = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    conversation = relationship("Conversation", back_populates="signup_forms")
    form_fields = relationship("FormField", back_populates="form")
    registrations = relationship("Registration", back_populates="form")


class FormField(Base):
    """Form field model for dynamic form fields"""
    __tablename__ = "form_fields"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    form_id = Column(UUID(as_uuid=True), ForeignKey("signup_forms.id"))
    field_name = Column(String, nullable=False)
    field_type = Column(String, nullable=False)  # text, email, phone, textarea, select
    label = Column(String, nullable=False)
    required = Column(Boolean, default=False)
    options = Column(JSON)  # For select fields
    order = Column(Integer, default=0)
    
    # Relationships
    form = relationship("SignupForm", back_populates="form_fields")


class Registration(Base):
    """Registration model for form submissions"""
    __tablename__ = "registrations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    form_id = Column(UUID(as_uuid=True), ForeignKey("signup_forms.id"))
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    additional_data = Column(JSON)
    registered_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    form = relationship("SignupForm", back_populates="registrations")