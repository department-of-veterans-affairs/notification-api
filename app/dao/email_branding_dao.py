from dataclasses import dataclass
import uuid


@dataclass
class EmailBrandingData:
    id: uuid.UUID
    name: str
    brand_type: str
    colour: str | None = None
    logo: str | None = None
    text: str | None = None
    alt_text: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
