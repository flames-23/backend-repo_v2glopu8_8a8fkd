"""
Database Schemas for the Smart Urban Travel Tool (SUTT)

Each Pydantic model corresponds to a MongoDB collection. The collection name
is the lowercase of the class name.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import date, datetime

class User(BaseModel):
    id: Optional[str] = Field(None, description="User ID (Mongo ObjectId as str)")
    name: str
    email: EmailStr
    language_pref: Optional[str] = Field(default="en")
    password_hash: Optional[str] = Field(None, description="BCrypt password hash")
    created_at: Optional[datetime] = None

class Place(BaseModel):
    id: Optional[str] = None
    name: str
    lat: float
    lng: float
    type: Optional[str] = None
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    capacity_estimate: Optional[int] = None

class Itinerary(BaseModel):
    id: Optional[str] = None
    user_id: str
    places: List[str] = Field(default_factory=list, description="List of place IDs")
    start_date: date
    end_date: date
    score: Optional[float] = None

class CameraAlert(BaseModel):
    id: Optional[str] = None
    camera_id: str
    timestamp: datetime
    alert_type: str
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    image_url: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

# Request/Response models
class ItineraryGenerateRequest(BaseModel):
    user_id: str
    dates: List[date]
    preferences: dict

class ItineraryGenerateResponse(BaseModel):
    itinerary_id: str
    user_id: str
    places: List[str]
    start_date: date
    end_date: date
    score: float

class ForecastNext7Response(BaseModel):
    place_id: str
    daily: List[dict]

class VisionAlertIn(BaseModel):
    camera_id: str
    timestamp: datetime
    alert_type: str
    confidence: float
    coords: Optional[dict] = None

class VisionAlertAck(BaseModel):
    status: str
    alert_id: str

class AuthRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class AuthRegisterResponse(BaseModel):
    user_id: str
    email: EmailStr
    name: str

class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
