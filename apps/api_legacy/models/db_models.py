from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("UserProfile", back_populates="user", uselist=False)
    saved_items = relationship("SavedItem", back_populates="user")
    events_created = relationship("UserEvent", back_populates="creator")
    rsvps = relationship("EventRSVP", back_populates="user")

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    old_city = Column(String)
    new_city = Column(String)
    preferences = Column(JSON)
    dislikes = Column(JSON)
    home_anchor = Column(JSON) # {lat, lng}
    work_anchor = Column(JSON) # {lat, lng}

    user = relationship("User", back_populates="profile")

class SavedItem(Base):
    __tablename__ = "saved_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_type = Column(String) # "place" | "event" | "task" | "route"
    item_ref = Column(String)
    snapshot = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="saved_items")

class UserEvent(Base):
    __tablename__ = "user_events"
    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, index=True)
    description = Column(String)
    city = Column(String, index=True)
    date = Column(DateTime(timezone=True))
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    
    creator = relationship("User", back_populates="events_created")
    rsvps = relationship("EventRSVP", back_populates="event")

class EventRSVP(Base):
    __tablename__ = "event_rsvps"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_id = Column(Integer, ForeignKey("user_events.id"))

    user = relationship("User", back_populates="rsvps")
    event = relationship("UserEvent", back_populates="rsvps")

class SourceAuditLog(Base):
    __tablename__ = "source_audit_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    endpoint = Column(String)
    live_apis_used = Column(JSON)
    db_queries_used = Column(JSON)
    fallback_triggers = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SettleTask(Base):
    __tablename__ = "settle_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    status = Column(String) # pending, completed
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AssistantSession(Base):
    __tablename__ = "assistant_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    session_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserInteraction(Base):
    """Tracks real user behavior: clicks, saves, views, rsvps, queries."""
    __tablename__ = "user_interactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    item_id = Column(String, nullable=True)         # place_id, event_id, service_id
    item_type = Column(String, nullable=True)        # "place" | "event" | "service"
    action_type = Column(String, nullable=False)     # "click" | "save" | "view" | "rsvp" | "query"
    domain = Column(String, nullable=True)           # "explore" | "work" | "connect" | "services" | "move"
    city = Column(String, nullable=True)
    query = Column(String, nullable=True)            # search query that led here
    item_categories = Column(JSON, nullable=True)    # place types / event category at interaction time
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ContextMemory(Base):
    """Persists recent user context for adaptive suggestions and ranking."""
    __tablename__ = "context_memory"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True, nullable=False)
    recent_searches = Column(JSON, default=list)     # [{query, domain, city, ts}, ...]
    recent_domains = Column(JSON, default=list)      # ["explore", "connect", ...]
    recent_locations = Column(JSON, default=list)    # [{lat, lng, label}, ...]
    category_affinities = Column(JSON, default=dict) # {"cafe": 12, "restaurant": 8, ...}
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
