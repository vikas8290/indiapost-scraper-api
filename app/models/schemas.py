from typing import List, Optional, Any
from pydantic import BaseModel, Field


class TrackingEvent(BaseModel):
    date: Optional[str] = Field(default=None, description="Event date e.g. 15/10/2026")
    time: Optional[str] = Field(default=None, description="Event time e.g. 14:30:20")
    office: Optional[str] = Field(default=None, description="Post office or processing center")
    event: Optional[str] = Field(default=None, description="Raw event text")
    event_type: Optional[str] = Field(default=None, description="Normalized event type")
    status: Optional[str] = Field(default=None, description="Status code at this event")


class TrackingResponse(BaseModel):
    success: bool
    consignment_number: str
    status: str = Field(
        default="pending",
        description="Current normalized status: pending, booked, in_transit, out_for_delivery, delivered, rto, rto_requested, cancelled"
    )
    current_status: Optional[str] = Field(default=None, description="Human readable latest status description")
    delivered: bool = Field(default=False, description="True if delivery completed")
    article_type: Optional[str] = Field(default="Speed Post", description="Type of postal article")
    booked_at: Optional[str] = Field(default=None, description="Booking post office name")
    booked_on: Optional[str] = Field(default=None, description="Booking timestamp or date")
    destination: Optional[str] = Field(default=None, description="Destination post office / city")
    destination_pincode: Optional[str] = Field(default=None, description="Destination PIN code")
    origin_pincode: Optional[str] = Field(default=None, description="Origin PIN code")
    delivered_at: Optional[str] = Field(default=None, description="Delivery timestamp if delivered")
    returned_at: Optional[str] = Field(default=None, description="Return timestamp if RTO")
    last_updated: Optional[str] = Field(default=None, description="Timestamp of latest scan")
    events_count: int = Field(default=0, description="Total number of scan events")
    events: List[TrackingEvent] = Field(default_factory=list, description="Chronological scan event history")
    error: Optional[str] = Field(default=None, description="Error message if tracking failed")
    source: Optional[str] = Field(default="self_hosted_scraper", description="Data source engine")


class TrackRequest(BaseModel):
    consignment_number: str = Field(..., description="Consignment number e.g. EE123456789IN")
