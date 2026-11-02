from typing import List, Optional, Any
from pydantic import BaseModel, Field


class TrackingEvent(BaseModel):
    date: Optional[str] = Field(default=None, description="Event date e.g. 15/10/2026 or 2026-10-27")
    time: Optional[str] = Field(default=None, description="Event time in 12-hour AM/PM format (Asia/Kolkata) e.g. 11:20 AM")
    time_24h: Optional[str] = Field(default=None, description="Raw 24-hour event time e.g. 11:20:30")
    time_am_pm: Optional[str] = Field(default=None, description="12-hour AM/PM event time e.g. 11:20 AM")
    datetime_formatted: Optional[str] = Field(default=None, description="Full formatted datetime in Asia/Kolkata e.g. 27 Oct 2026, 11:20 AM")
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
    booked_on_formatted: Optional[str] = Field(default=None, description="Booking datetime in 12h AM/PM Asia/Kolkata e.g. 27 Oct 2026, 11:20 AM")
    destination: Optional[str] = Field(default=None, description="Destination post office / city")
    destination_pincode: Optional[str] = Field(default=None, description="Destination PIN code")
    origin_pincode: Optional[str] = Field(default=None, description="Origin PIN code")
    delivered_at: Optional[str] = Field(default=None, description="Delivery timestamp if delivered")
    delivered_at_formatted: Optional[str] = Field(default=None, description="Delivery datetime in 12h AM/PM Asia/Kolkata")
    returned_at: Optional[str] = Field(default=None, description="Return timestamp if RTO")
    returned_at_formatted: Optional[str] = Field(default=None, description="Return datetime in 12h AM/PM Asia/Kolkata e.g. 29 Oct 2026, 05:26 PM")
    last_updated: Optional[str] = Field(default=None, description="Timestamp of latest scan")
    events_count: int = Field(default=0, description="Total number of scan events")
    events: List[TrackingEvent] = Field(default_factory=list, description="Chronological scan event history")
    error: Optional[str] = Field(default=None, description="Error message if tracking failed")
    source: Optional[str] = Field(default="self_hosted_scraper", description="Data source engine")


class TrackRequest(BaseModel):
    consignment_number: str = Field(..., description="Consignment number e.g. EE123456789IN")
