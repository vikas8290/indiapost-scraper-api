import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from app.models.schemas import TrackingResponse, TrackingEvent


def determine_event_status(
    event_desc: Optional[str],
    event_code: Optional[str] = None,
    remarks: Optional[str] = None
) -> str:
    """
    Derives a clear, human-readable status for an individual tracking event.
    Examples: Delivered, Out for Delivery, In Transit, Booked, Returned / RTO, Delivery Attempted
    """
    rem = (remarks or "").strip()
    if rem and rem.lower() not in ["", "none", "null"]:
        return rem

    code = (event_code or "").upper()
    desc = (event_desc or "").lower()

    if "out for delivery" in desc or "out_for_delivery" in desc or "item_invoice" in code or "out for delivery" in code:
        return "Out for Delivery"
    if "deliver" in code or "deliver" in desc:
        return "Delivered"
    if any(r in desc for r in ["return", "rto", "undeliver"]) or "RETURN" in code or "UNDELIVER" in code:
        return "Returned / RTO"
    if any(u in desc for u in ["door locked", "refused", "insufficient", "addressee"]) and "deliver" not in desc:
        return "Delivery Attempted"
    if "book" in code or "book" in desc:
        return "Booked"
    if any(d in code for d in ["DISPATCH", "RECEIVE", "BAG", "TRANSIT", "FORWARD", "OPEN"]) or any(d in desc for d in ["dispatch", "received", "bag", "transit"]):
        return "In Transit"

    return "In Transit" if event_desc else "Pending"


def format_ist_time(time_str: Optional[str]) -> Optional[str]:
    """
    Converts 24-hour or raw time into 12-hour AM/PM format (Asia/Kolkata).
    Examples:
      '11:20:30' -> '11:20 AM'
      '17:01:38' -> '05:01 PM'
      '00:09:24' -> '12:09 AM'
    """
    if not time_str:
        return None
    s = str(time_str).strip().replace("Z", "")
    if " " in s and any(m in s.upper() for m in ["AM", "PM"]):
        return s

    s = s.split(".")[0]
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            t = datetime.strptime(s, fmt)
            return t.strftime("%I:%M %p")
        except ValueError:
            continue
    return s


def format_ist_datetime(date_str: Optional[str], time_str: Optional[str] = None) -> Optional[str]:
    """
    Formats dates and times into standard 12-hour AM/PM format in Asia/Kolkata (IST).
    Examples:
      '2026-10-27T11:20:30Z' -> '27 Oct 2026, 11:20 AM'
      '2026-10-27', '17:01:38' -> '27 Oct 2026, 05:01 PM'
    """
    if not date_str and not time_str:
        return None

    s = (date_str or "").strip().replace("Z", "")
    t = (time_str or "").strip().replace("Z", "") if time_str else None

    if "T" in s:
        parts = s.split("T")
        s = parts[0]
        if not t and len(parts) > 1:
            t = parts[1]

    if t:
        clean_t = t.split(".")[0]
        full = f"{s} {clean_t}"
    else:
        full = s

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d %I:%M:%S %p",
        "%Y-%m-%d %I:%M %p",
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %I:%M %p",
        "%d-%m-%Y %I:%M:%S %p",
        "%d-%m-%Y %I:%M %p",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ):
        try:
            dt = datetime.strptime(full, fmt)
            if any(k in fmt for k in ("%H", "%I")):
                return dt.strftime("%d %b %Y, %I:%M %p")
            return dt.strftime("%d %b %Y")
        except ValueError:
            continue

    return full


def find_rto_event(events: List[TrackingEvent]) -> Optional[TrackingEvent]:
    """
    Finds if any event in the tracking history indicates a return/RTO.
    """
    for ev in events:
        desc = (ev.event or "").lower()
        code = (ev.event_type or "").lower()
        st = (ev.status or "").lower()

        if (
            "item_return" in code or
            "itemreturn" in code or
            "rto" in code or
            "return" in code or
            "returned to sender" in desc or
            "item returned" in desc or
            "return to sender" in desc or
            "returned" in desc or
            "rto" in desc or
            "undelivered" in desc or
            "unclaimed" in desc or
            st in [
                "refused", "unclaimed", "door locked", "addressee left",
                "insufficient address", "returned / rto", "rto", "not delivered"
            ]
        ):
            return ev
    return None


def normalize_status(current_status: str, events: List[TrackingEvent]) -> str:
    """
    Normalizes overall consignment status string into standard lifecycle states:
    pending, booked, in_transit, out_for_delivery, delivered, rto, rto_requested, cancelled
    """
    text = (current_status or "").lower()

    # Cancelled check
    if "cancel" in text:
        return "cancelled"

    # Check if this consignment was returned to sender (RTO)
    rto_ev = find_rto_event(events)
    if rto_ev or "returned" in text or "return" in text or "rto" in text:
        return "rto"

    # Delivered check
    if "delivered" in text or "delivery confirmed" in text:
        return "delivered"

    # Check last event if available
    if events:
        last_event = events[0]  # Usually newest event is first
        last_text = (last_event.event or "").lower()

        if "delivered" in last_text:
            return "delivered"
        if "out for delivery" in last_text or "item_invoice" in (last_event.event_type or "").lower():
            return "out_for_delivery"
        if any(r in last_text for r in ["return", "rto", "returned to sender", "undelivered"]):
            return "rto"
        if any(u in last_text for u in ["door locked", "refused", "insufficient address", "addressee"]):
            return "rto_requested"
        if any(d in last_text for d in ["dispatched", "received", "bagged", "transit"]):
            return "in_transit"
        if "booked" in last_text:
            return "booked"

    if "out for delivery" in text:
        return "out_for_delivery"

    if any(w in text for w in ["dispatch", "transit", "received", "bag"]):
        return "in_transit"

    if "booked" in text:
        return "booked"

    return "in_transit" if events else "pending"


def parse_indiapost_json(data: Dict[str, Any], consignment_no: str) -> Optional[TrackingResponse]:
    """
    Parses tracking results from India Post Next.js backend JSON response.
    """
    if not data:
        return None

    booking = data.get("booking_details", {}) or {}
    del_status = data.get("del_status", {}) or {}
    raw_events = data.get("tracking_details", []) or []

    # If article_number is null and no events exist, the article was never booked/found
    if not booking.get("article_number") and not raw_events:
        return None

    events: List[TrackingEvent] = []
    for ev in raw_events:
        raw_date = ev.get("date") or ""
        date_formatted = raw_date.split("T")[0] if "T" in raw_date else raw_date
        time_raw = ev.get("time") or ""
        time_ampm = format_ist_time(time_raw)
        datetime_formatted = format_ist_datetime(date_formatted, time_raw)
        office = ev.get("office")
        event_desc = ev.get("event")
        event_code = (ev.get("eventcode") or "").lower()
        remarks = ev.get("remarks")

        event_status = determine_event_status(
            event_desc=event_desc,
            event_code=event_code,
            remarks=remarks
        )

        events.append(TrackingEvent(
            date=date_formatted,
            time=time_ampm or time_raw,
            time_24h=time_raw,
            time_am_pm=time_ampm,
            datetime_formatted=datetime_formatted,
            office=office,
            event=event_desc,
            event_type=event_code or (event_desc.lower().replace(" ", "_") if event_desc else None),
            status=event_status
        ))

    delivery_confirmed_on = booking.get("delivery_confirmed_on")
    raw_status = del_status.get("del_status") or (events[0].event if events else "in_transit")
    norm_status = normalize_status(raw_status, events)

    rto_ev = find_rto_event(events)
    returned_at = None
    if rto_ev:
        norm_status = "rto"
        if rto_ev.date and rto_ev.time:
            returned_at = f"{rto_ev.date} {rto_ev.time}"
        elif rto_ev.date:
            returned_at = rto_ev.date

    delivered = (norm_status == "delivered") or (bool(delivery_confirmed_on) and norm_status != "rto")

    latest_event = events[0] if events else None
    if norm_status == "rto":
        reason = f" ({rto_ev.status})" if (rto_ev and rto_ev.status and rto_ev.status.lower() not in ["in transit", "pending", "booked", "delivered", "returned / rto"]) else ""
        if latest_event and latest_event != rto_ev and latest_event.office:
            current_status = f"Returned to Sender{reason} - {latest_event.event} at {latest_event.office}"
        elif latest_event and latest_event != rto_ev:
            current_status = f"Returned to Sender{reason} - {latest_event.event}"
        elif latest_event and latest_event.office:
            current_status = f"Item Returned to Sender{reason} at {latest_event.office}"
        else:
            current_status = f"Item Returned to Sender{reason}"
    elif latest_event and latest_event.office:
        current_status = f"{latest_event.event} at {latest_event.office}"
    elif latest_event:
        current_status = latest_event.event
    else:
        current_status = raw_status

    destination = booking.get("destination_office_name") or booking.get("destination_city")

    # Reverse events to display in chronological order (from booking to delivery)
    events_reversed = list(reversed(events))

    raw_booking_date = booking.get("booking_date")
    clean_booking_date = raw_booking_date.replace("Z", "").replace("T", " ") if raw_booking_date else None
    booked_on_formatted = format_ist_datetime(raw_booking_date)
    returned_at_formatted = format_ist_datetime(returned_at) if returned_at else None
    delivered_at_formatted = format_ist_datetime(delivery_confirmed_on) if delivery_confirmed_on else None

    return TrackingResponse(
        success=True,
        consignment_number=consignment_no,
        status=norm_status,
        current_status=current_status,
        delivered=delivered,
        article_type=booking.get("article_type", "Speed Post"),
        booked_at=booking.get("booking_office_name"),
        booked_on=clean_booking_date or raw_booking_date,
        booked_on_formatted=booked_on_formatted,
        destination=destination,
        destination_pincode=booking.get("destination_pincode"),
        origin_pincode=booking.get("booking_pin"),
        delivered_at=delivery_confirmed_on,
        delivered_at_formatted=delivered_at_formatted,
        returned_at=returned_at,
        returned_at_formatted=returned_at_formatted,
        last_updated=latest_event.date if latest_event else None,
        events_count=len(events_reversed),
        events=events_reversed,
        source="indiapost_portal_scraper"
    )


def parse_indiapost_html(html: str) -> Dict[str, Any]:
    """
    Parses tracking results from legacy India Post TrackConsignment HTML output.
    """
    soup = BeautifulSoup(html, "html.parser")

    booked_at = None
    booked_on = None
    destination = None
    dest_pincode = None
    article_type = "Speed Post"
    delivered_at = None
    current_status = None
    events: List[TrackingEvent] = []

    # Look for Article summary table
    summary_table = soup.find("table", {"id": re.compile(r"gvTrckMailArticleDtlsOER|gvTrckMailArticleDetails|article", re.I)})
    if summary_table:
        rows = summary_table.find_all("tr")
        if len(rows) > 1:
            cells = [c.get_text(strip=True) for c in rows[1].find_all(["td", "th"])]
            if len(cells) >= 6:
                booked_at = cells[0] if cells[0] else None
                booked_on = cells[1] if cells[1] else None
                dest_pincode = cells[2] if cells[2] else None
                article_type = cells[4] if len(cells) > 4 and cells[4] else "Speed Post"
                destination = cells[5] if len(cells) > 5 and cells[5] else None
            if len(cells) >= 7 and "delivered" in cells[6].lower():
                delivered_at = cells[6]

    # Look for Event timeline table
    event_table = soup.find("table", {"id": re.compile(r"gvTrackEventsOER|gvTrackEvents|events|Grid", re.I)})
    if not event_table:
        tables = soup.find_all("table")
        for tbl in tables:
            header_text = tbl.get_text().lower()
            if "event" in header_text and ("office" in header_text or "date" in header_text):
                event_table = tbl
                break

    if event_table:
        rows = event_table.find_all("tr")
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cols) >= 4 and not any(h in cols[0].lower() for h in ["date", "s.no", "event"]):
                date_val = cols[0]
                time_raw = cols[1]
                time_ampm = format_ist_time(time_raw)
                datetime_formatted = format_ist_datetime(date_val, time_raw)
                office_val = cols[2]
                event_val = cols[3]

                event_status = determine_event_status(
                    event_desc=event_val,
                    event_code=None
                )

                ev = TrackingEvent(
                    date=date_val,
                    time=time_ampm or time_raw,
                    time_24h=time_raw,
                    time_am_pm=time_ampm,
                    datetime_formatted=datetime_formatted,
                    office=office_val,
                    event=event_val,
                    event_type=event_val.lower().replace(" ", "_"),
                    status=event_status
                )
                events.append(ev)

    rto_ev = find_rto_event(events)
    returned_at = None
    if rto_ev:
        if rto_ev.date and rto_ev.time:
            returned_at = f"{rto_ev.date} {rto_ev.time}"
        elif rto_ev.date:
            returned_at = rto_ev.date

    if events:
        latest = events[0]
        if rto_ev:
            reason = f" ({rto_ev.status})" if (rto_ev.status and rto_ev.status.lower() not in ["in transit", "pending", "booked", "delivered", "returned / rto"]) else ""
            if latest != rto_ev and latest.office:
                current_status = f"Returned to Sender{reason} - {latest.event} at {latest.office}"
            elif latest != rto_ev:
                current_status = f"Returned to Sender{reason} - {latest.event}"
            elif latest.office:
                current_status = f"Item Returned to Sender{reason} at {latest.office}"
            else:
                current_status = f"Item Returned to Sender{reason}"
        else:
            current_status = f"{latest.event} at {latest.office}"
            if "delivered" in latest.event.lower():
                delivered_at = f"{latest.date} {latest.time}".strip()

    status = normalize_status(current_status or "", events)
    if rto_ev:
        status = "rto"

    return {
        "status": status,
        "current_status": current_status,
        "delivered": status == "delivered",
        "article_type": article_type,
        "booked_at": booked_at,
        "booked_on": booked_on,
        "booked_on_formatted": format_ist_datetime(booked_on),
        "destination": destination,
        "destination_pincode": dest_pincode,
        "delivered_at": delivered_at,
        "delivered_at_formatted": format_ist_datetime(delivered_at),
        "returned_at": returned_at,
        "returned_at_formatted": format_ist_datetime(returned_at),
        "events": list(reversed(events)),
        "events_count": len(events)
    }
