from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.identity import EmailAddress

PASSWORD_MIN_LENGTH = 4
PASSWORD_MAX_LENGTH = 1024


class SafeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    @field_validator("*", mode="before")
    @classmethod
    def valid_unicode(cls, value):
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise ValueError("Invalid Unicode") from None
        return value


Profession = Literal[
    "CLINICIAN", "RESEARCHER", "DATA_SCIENTIST", "NLP_ENGINEER", "STUDENT", "OTHER"
]
Locale = Literal[
    "en", "es", "ca", "cs", "da", "de", "el", "et", "fr", "it", "nl", "no", "pt", "ro", "ru", "sv"
]


class Profile(SafeModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    full_name: str = Field(min_length=1, max_length=120)
    institution: str = Field(min_length=1, max_length=200)
    professional_role: Profession
    professional_role_other: str = Field(default="", max_length=200)
    preferred_locale: Locale = "en"

    @field_validator("full_name", "institution", "professional_role_other")
    @classmethod
    def clean(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Invalid profile")
        return value.strip()

    @model_validator(mode="after")
    def other(self):
        if not self.full_name or not self.institution:
            raise ValueError("Invalid profile")
        if self.professional_role == "OTHER" and not self.professional_role_other:
            raise ValueError("Other requires a description")
        if self.professional_role != "OTHER":
            self.professional_role_other = ""
        return self


class Register(Profile):
    email: EmailAddress
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    password_confirmation: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    legal_accepted: bool

    @field_validator("email", mode="after")
    @classmethod
    def normalize(cls, value):
        return str(value).lower()

    @model_validator(mode="after")
    def confirmation(self):
        if not self.legal_accepted or self.password != self.password_confirmation:
            raise ValueError("Confirm password and legal notice")
        return self


class Login(SafeModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: EmailAddress
    password: str = Field(min_length=1, max_length=1024)
    otp: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9-]*$")


class PasswordChange(SafeModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    current_password: str = Field(max_length=1024)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    password_confirmation: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )

    @model_validator(mode="after")
    def confirmation(self):
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match")
        return self


class AdminChange(SafeModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    access_tier: Literal["STANDARD", "EXTENDED", "UNLIMITED"] | None = None
    account_status: Literal["ACTIVE", "SUSPENDED"] | None = None
    system_role: Literal["USER", "ADMIN"] | None = None
