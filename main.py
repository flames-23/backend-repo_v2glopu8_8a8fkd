import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import jwt
import bcrypt
import requests

from database import db, create_document, get_documents
from schemas import (
    User, Place, Itinerary, CameraAlert,
    ItineraryGenerateRequest, ItineraryGenerateResponse,
    ForecastNext7Response, VisionAlertIn, VisionAlertAck,
    AuthRegisterRequest, AuthRegisterResponse, Token
)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

app = FastAPI(title="SUTT API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        docs = get_documents("user", {"email": email}, limit=1)
        if not docs:
            raise HTTPException(status_code=401, detail="User not found")
        doc = docs[0]
        return User(
            id=str(doc.get("_id")),
            name=doc.get("name"),
            email=doc.get("email"),
            language_pref=doc.get("language_pref"),
            created_at=doc.get("created_at"),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/")
def root():
    return {"message": "SUTT API is running"}


# Auth Endpoints
@app.post("/auth/register", response_model=AuthRegisterResponse)
def register(req: AuthRegisterRequest):
    existing = get_documents("user", {"email": req.email}, limit=1)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user = User(name=req.name, email=req.email, password_hash=password_hash)
    user_id = create_document("user", user)
    return AuthRegisterResponse(user_id=user_id, email=req.email, name=req.name)


@app.post("/auth/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    docs = get_documents("user", {"email": form_data.username}, limit=1)
    if not docs:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    doc = docs[0]
    if not bcrypt.checkpw(form_data.password.encode(), doc.get("password_hash", "").encode()):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    access_token = create_access_token({"sub": doc.get("email")})
    return Token(access_token=access_token)


# Itinerary Service Proxy
@app.post("/api/itinerary/generate", response_model=ItineraryGenerateResponse)
def itinerary_generate(req: ItineraryGenerateRequest, user: User = Depends(get_current_user)):
    # Simple mock recommender: choose up to 5 top-rated places
    places = get_documents("place", {}, limit=50)
    places_sorted = sorted(places, key=lambda p: p.get("rating", 0), reverse=True)
    selected = [str(p.get("_id")) for p in places_sorted[:5]]
    start_date = min(req.dates)
    end_date = max(req.dates)
    score = 0.5 + min(len(selected), 5) * 0.1
    itinerary = Itinerary(user_id=user.id or "", places=selected, start_date=start_date, end_date=end_date, score=score)
    itinerary_id = create_document("itinerary", itinerary)
    return ItineraryGenerateResponse(
        itinerary_id=itinerary_id,
        user_id=user.id or "",
        places=selected,
        start_date=start_date,
        end_date=end_date,
        score=score,
    )


# Forecast Service Proxy (stub combining OpenWeather as external)
@app.get("/api/forecast/next7", response_model=ForecastNext7Response)
def forecast_next7(place_id: str, user: User = Depends(get_current_user)):
    docs = get_documents("place", {"_id": {"$exists": True}})
    target = next((p for p in docs if str(p.get("_id")) == place_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Place not found")
    daily = []
    base_flow = int((target.get("rating", 3) or 3) * 100)
    for i in range(7):
        day = datetime.now(timezone.utc) + timedelta(days=i)
        val = base_flow + (i * 5)
        daily.append({"date": day.date().isoformat(), "flow": val})
    return ForecastNext7Response(place_id=place_id, daily=daily)


# Vision Alerts Intake
@app.post("/api/vision/alerts", response_model=VisionAlertAck)
def vision_alerts(alert: VisionAlertIn, user: User = Depends(get_current_user)):
    lat = alert.coords.get("lat") if alert.coords else None
    lng = alert.coords.get("lng") if alert.coords else None
    doc = CameraAlert(
        camera_id=alert.camera_id,
        timestamp=alert.timestamp,
        alert_type=alert.alert_type,
        confidence=alert.confidence,
        lat=lat,
        lng=lng,
    )
    alert_id = create_document("cameraalert", doc)
    return VisionAlertAck(status="ok", alert_id=alert_id)


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db as _db
        if _db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = _db.name if hasattr(_db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = _db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
