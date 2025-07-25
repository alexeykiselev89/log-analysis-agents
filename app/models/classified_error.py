from pydantic import BaseModel

class ClassifiedError(BaseModel):
    original_message: str
    normalized_message: str
    frequency: int
    level: str
    criticality: str = "низкая"
