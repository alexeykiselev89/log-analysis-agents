from pydantic import BaseModel
from datetime import datetime

class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    thread: str
    class_name: str
    message: str
