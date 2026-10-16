import re
from typing import List, Dict, Any, Tuple
from bs4 import BeautifulSoup
from app.models.schemas import TrackingEvent


def normalize_status(current_status: str, events: List[TrackingEvent]) -> str:
    """
    Normalizes status string into standard lifecycle states:
    pending, booked, in_transit, out_for_delivery, delivered, rto, rto_requested, cancelled
    """
    text = (current_status or "").lower()

    # Cancelled check
    if "cancel" in text:
        return "cancelled"

    # Delivered check
    if "delivered" in text or "delivery confirmed" in text:
        return "delivered"

    # RTO / Returned check
    if "returned" in text or "return" in text or "rto" in text:
        return "rto"

    # Check last event if available
    if events:
        last_event = events[0]  # Usually newest event is first
        last_text = (last_event.event or "").lower()

        if "delivered" in last_text:
            return "delivered"
        if "out for delivery" in last_text:
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


def parse_indiapost_html(html: str) -> Dict[str, Any]:
    """
    Parses tracking results from India Post TrackConsignment HTML output.
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
            # India Post table headers usually:
            # [Booked At, Booked On, Destination Pincode, Tariff, Article Type, Delivery Location, Event Date/Status]
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
        # Fallback to any second table with date/time columns
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
                time_val = cols[1]
                office_val = cols[2]
                event_val = cols[3]

                ev = TrackingEvent(
                    date=date_val,
                    time=time_val,
                    office=office_val,
                    event=event_val,
                    event_type=event_val.lower().replace(" ", "_"),
                )
                events.append(ev)

    if events:
        latest = events[0]
        current_status = f"{latest.event} at {latest.office}"
        if "delivered" in latest.event.lower():
            delivered_at = f"{latest.date} {latest.time}".strip()

    status = normalize_status(current_status or "", events)

    return {
        "status": status,
        "current_status": current_status,
        "delivered": status == "delivered",
        "article_type": article_type,
        "booked_at": booked_at,
        "booked_on": booked_on,
        "destination": destination,
        "destination_pincode": dest_pincode,
        "delivered_at": delivered_at,
        "events": events,
        "events_count": len(events)
    }
