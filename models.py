from sqlalchemy import Column, String, Float, Integer, Boolean, ForeignKey, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid
import enum


def generate_uuid():
    """Generate a UUID string for primary keys."""
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.MANAGER, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Site(Base):
    __tablename__ = "sites"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)

    # Site Info / About fields
    site_code = Column(String(100), nullable=True)          # Generated but can be edited
    site_type = Column(String(50), nullable=True)           # 4G, 5G, Fiber, etc.
    region = Column(String(255), nullable=True)             # Location/region
    location = Column(String(255), nullable=True)           # Detailed location
    latitude = Column(Float, nullable=True)                 # GPS coordinates
    longitude = Column(Float, nullable=True)                # GPS coordinates
    google_maps_url = Column(Text, nullable=True)           # Google Maps link
    images = Column(Text, nullable=True)                    # JSON array of image URLs
    notes = Column(Text, nullable=True)                     # Site notes / comments
    is_archived = Column(Boolean, default=False)            # Allow archive inactive sites

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    labor_cost = Column(Float, default=0.0)

    materials = relationship("Material", back_populates="site", cascade="all, delete")
    activities = relationship("Activity", back_populates="site", cascade="all, delete")
    operational_costs = relationship("OperationalCost", back_populates="site", cascade="all, delete")


class Material(Base):
    __tablename__ = "materials"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String)
    quantity = Column(Float)
    unit = Column(String)
    cost = Column(Float)
    site_id = Column(String, ForeignKey("sites.id"))
    site = relationship("Site", back_populates="materials")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)  # When activity was completed

    # New: Dates when creating activities
    activity_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    site_id = Column(String, ForeignKey("sites.id"))
    site = relationship("Site", back_populates="activities")


class OperationalCost(Base):
    __tablename__ = "operational_costs"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String)
    amount = Column(Float)
    site_id = Column(String, ForeignKey("sites.id"))
    site = relationship("Site", back_populates="operational_costs")


class CompanySetting(Base):
    """
    Company settings singleton-ish table. The application currently uses
    a single row (id='company') to store company-level configuration
    like Name and Logo.
    """
    __tablename__ = "company_settings"

    id = Column(String, primary_key=True, default="company")
    name = Column(String(255), nullable=True)
    logo_url = Column(Text, nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    website = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())