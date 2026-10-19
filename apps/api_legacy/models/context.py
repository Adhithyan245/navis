from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class Coordinates(BaseModel):
    lat: float
    lng: float


class UserContext(BaseModel):
    """
    Flexible user context model used across:
    - onboarding
    - voice queries
    - orchestration
    - planner DAG execution

    All fields are optional to prevent
    validation failures during partial requests.
    """

    # Core identity
    user_id: Optional[str] = None

    # Relocation context
    old_city: Optional[str] = None
    new_city: Optional[str] = None

    # Location context
    neighborhood: Optional[str] = None
    work_area: Optional[str] = None

    # Preferences
    preferences: List[str] = Field(default_factory=list)
    dislikes: List[str] = Field(default_factory=list)

    # Lifestyle
    insurance: Optional[str] = None
    budget: Optional[str] = None            # low | medium | high
    work_style: Optional[str] = None        # remote | hybrid | office
    mobility_preference: Optional[str] = None  # transit | bike | car | walk

    # Food / social
    food_preferences: List[str] = Field(default_factory=list)
    event_categories: List[str] = Field(default_factory=list)

    # Historical memory
    favorite_old_city_places: List[str] = Field(default_factory=list)

    # Geo anchors
    home_anchor: Optional[Coordinates] = None
    work_anchor: Optional[Coordinates] = None

    # Extra extensibility
    metadata: Dict[str, str] = Field(default_factory=dict)