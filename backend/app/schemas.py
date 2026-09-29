from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

FieldType = Literal["text", "number", "date", "url", "boolean"]


class DataField(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=80)
    type: FieldType
    description: str = Field(default="", max_length=240)


class DraftRequest(BaseModel):
    prompt: str = Field(min_length=15, max_length=3000)


class ApproveRequest(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    queries: list[str] = Field(min_length=1, max_length=3)
    fields: list[DataField] = Field(min_length=1, max_length=20)
    identity_fields: list[str] = Field(min_length=1, max_length=4)

    @field_validator("queries")
    @classmethod
    def check_queries(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 200 for item in value):
            raise ValueError("Queries must be 1 to 200 characters")
        return [item.strip() for item in value]

    @model_validator(mode="after")
    def check_identity(self) -> "ApproveRequest":
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Field names must be unique")
        if len(self.identity_fields) != len(set(self.identity_fields)) or not set(
            self.identity_fields
        ) <= set(names):
            raise ValueError("Identity fields must be unique approved fields")
        return self


class ScheduleRequest(BaseModel):
    cadence: Literal["none", "daily", "weekly"]
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    local_hour: int = Field(default=9, ge=0, le=23)
    week_day: int = Field(default=0, ge=0, le=6)
