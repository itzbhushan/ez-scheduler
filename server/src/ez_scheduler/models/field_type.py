"""Enums for the application"""

from enum import Enum


class FieldType(str, Enum):
    """Enum for form field types"""

    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    CHECKBOX = "checkbox"
