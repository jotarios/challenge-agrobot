"""Pydantic schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from src.models.alert_rule import Operator


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    metric_type: str = Field(min_length=1, max_length=50)
    operator: Operator
    threshold_value: float


class RuleUpdate(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    metric_type: str | None = Field(default=None, min_length=1, max_length=50)
    operator: Operator | None = None
    threshold_value: float | None = None


class RuleResponse(BaseModel):
    id: int
    user_id: int
    location_h3_index: str
    metric_type: str
    operator: str
    threshold_value: float
    last_notified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Composite Rule (RuleGroup) schemas ───────────────────────


class ConditionCreate(BaseModel):
    metric_type: str = Field(min_length=1, max_length=50)
    operator: Operator
    threshold_value: float


class ConditionResponse(BaseModel):
    id: int
    metric_type: str
    operator: str
    threshold_value: float

    model_config = {"from_attributes": True}


class RuleGroupCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    logic: str = Field(default="and", pattern="^(and|or)$")
    conditions: list[ConditionCreate] = Field(min_length=2, max_length=10)


class RuleGroupUpdate(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    logic: str | None = Field(default=None, pattern="^(and|or)$")
    conditions: list[ConditionCreate] | None = Field(default=None, min_length=2, max_length=10)


class RuleGroupResponse(BaseModel):
    id: int
    user_id: int
    location_h3_index: str
    logic: str
    conditions: list[ConditionResponse]
    last_notified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
