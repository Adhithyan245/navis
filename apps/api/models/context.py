from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Coordinates(BaseModel):
    lat: float
    lng: float

    def get(self, key: str, default: Any = None) -> Any:
        if key == "lat":
            return self.lat
        if key in ("lng", "lon"):
            return self.lng
        return default

    def __getitem__(self, item: str) -> Any:
        if item == "lat":
            return self.lat
        if item in ("lng", "lon"):
            return self.lng
        raise KeyError(item)

class UserLocation(BaseModel):
    lat: float
    lon: float
    city: Optional[str] = None
    country: Optional[str] = None

class UserContext(BaseModel):
    # Modern context fields
    location: Optional[UserLocation] = None
    time_available_hours: Optional[float] = None

    # Legacy context fields for full backwards-compatibility
    user_id: Optional[str] = None
    old_city: Optional[str] = None
    new_city: Optional[str] = None
    neighborhood: Optional[str] = None
    work_area: Optional[str] = None
    preferences: List[str] = Field(default_factory=list)
    dislikes: List[str] = Field(default_factory=list)
    insurance: Optional[str] = None
    budget: Optional[str] = None            # low | medium | high
    work_style: Optional[str] = None        # remote | hybrid | office
    mobility_preference: Optional[str] = None  # transit | bike | car | walk
    food_preferences: List[str] = Field(default_factory=list)
    event_categories: List[str] = Field(default_factory=list)
    favorite_old_city_places: List[str] = Field(default_factory=list)
    home_anchor: Optional[Coordinates] = None
    work_anchor: Optional[Coordinates] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
