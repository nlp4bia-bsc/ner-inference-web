"""Syntactic email normalization; ownership and verification are separate policies."""

from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator


def normalize_email(value):
    try:
        # Reserved .test addresses are valid for synthetic deployments. Syntax
        # validation does not claim mailbox ownership; verification is optional.
        return validate_email(
            value, check_deliverability=False, test_environment=True
        ).normalized.lower()
    except EmailNotValidError:
        raise ValueError("Invalid email") from None


EmailAddress = Annotated[str, AfterValidator(normalize_email)]
