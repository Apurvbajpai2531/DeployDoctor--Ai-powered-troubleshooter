from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    service: str = Field(examples=["DeployDoctor"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["development"])
    uptime_seconds: float = Field(examples=[12.5])
    timestamp: datetime
