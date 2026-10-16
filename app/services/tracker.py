import re
import os
import time
import logging
from typing import Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from cachetools import TTLCache

from app.models.schemas import TrackingResponse, TrackingEvent
from app.services.captcha_solver import solve_text_captcha, solve_image_captcha
from app.services.parser import parse_indiapost_html

logger = logging.getLogger("indiapost_tracker")

INDIAPOST_PORTAL_URL = "https://www.indiapost.gov.in/_layouts/15/dop.portal.tracking/trackconsignment.aspx"
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "900"))  # 15 minutes


class IndiaPostTrackerService:
    def __init__(self):
        # Cache up to 1000 items with TTL
        self.cache = TTLCache(maxsize=1000, ttl=CACHE_TTL)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

    def track(self, consignment_no: str) -> TrackingResponse:
        consignment_no = (consignment_no or "").strip().upper()

        # Validate standard 13-character India Post format (e.g., EE123456789IN)
        if not re.match(r'^[A-Z]{2}[0-9]{9}[A-Z]{2}$', consignment_no):
            return TrackingResponse(
                success=False,
                consignment_number=consignment_no,
                status="pending",
                error="Invalid India Post consignment number format. Expected format: 2 letters, 9 digits, 2 letters (e.g. EE123456789IN)"
            )

        # Check Cache
        if consignment_no in self.cache:
            logger.info(f"Returning cached tracking response for {consignment_no}")
            cached_data = self.cache[consignment_no]
            return cached_data

        # Attempt 1: Direct India Post Portal
        result = self._track_via_portal(consignment_no)
        if result and result.success:
            self.cache[consignment_no] = result
            return result

        # Attempt 2: Official CEPT API (if credentials present)
        cept_result = self._track_via_cept_api(consignment_no)
        if cept_result and cept_result.success:
            self.cache[consignment_no] = cept_result
            return cept_result

        # Return fallback if not found or temporary portal error
        return TrackingResponse(
            success=False,
            consignment_number=consignment_no,
            status="pending",
            error=result.error if result else "Consignment details not available or portal temporarily unreachable"
        )

    def _track_via_portal(self, consignment_no: str) -> Optional[TrackingResponse]:
        """
        Scrapes the official India Post WebForms tracking page.
        """
        session = requests.Session()
        session.headers.update(self.headers)

        try:
            # Step 1: GET tracking page to retrieve ViewState and Captcha
            resp = session.get(INDIAPOST_PORTAL_URL, timeout=12)
            if resp.status_code != 200:
                logger.warning(f"IndiaPost portal returned status {resp.status_code}")
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract ASP.NET hidden fields
            viewstate = soup.find("input", {"id": "__VIEWSTATE"})
            viewstategen = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
            eventvalidation = soup.find("input", {"id": "__EVENTVALIDATION"})

            if not viewstate:
                logger.error("Could not find __VIEWSTATE on India Post page")
                return None

            viewstate_val = viewstate.get("value", "")
            viewstategen_val = viewstategen.get("value", "") if viewstategen else ""
            eventvalidation_val = eventvalidation.get("value", "") if eventvalidation else ""

            # Step 2: Solve Captcha
            captcha_ans = None

            # Check math question label
            captcha_lbl = soup.find("span", {"id": re.compile(r"lblCaptcha|Captcha|ucOERControl", re.I)})
            if captcha_lbl:
                captcha_ans = solve_text_captcha(captcha_lbl.get_text())

            # If not solved from label, check captcha image
            if not captcha_ans:
                img_elem = soup.find("img", {"id": re.compile(r"imgCaptcha|Captcha", re.I)})
                if img_elem and img_elem.get("src"):
                    src = img_elem.get("src")
                    if src.startswith("data:image"):
                        # Base64 image
                        import base64
                        b64_data = src.split(",", 1)[1]
                        captcha_ans = solve_image_captcha(base64.b64decode(b64_data))
                    else:
                        img_url = requests.compat.urljoin(INDIAPOST_PORTAL_URL, src)
                        img_resp = session.get(img_url, timeout=6)
                        if img_resp.status_code == 200:
                            captcha_ans = solve_image_captcha(img_resp.content)

            if not captcha_ans:
                logger.warning("Could not automatically solve captcha on this attempt")
                return None

            # Step 3: POST tracking query
            payload = {
                "__VIEWSTATE": viewstate_val,
                "__VIEWSTATEGENERATOR": viewstategen_val,
                "__EVENTVALIDATION": eventvalidation_val,
                "ctl00$PlaceHolderMain$ucOERControl$txtSearch": consignment_no,
                "ctl00$PlaceHolderMain$ucOERControl$txtCaptcha": captcha_ans,
                "ctl00$PlaceHolderMain$ucOERControl$btnSearch": "Track Now"
            }

            post_resp = session.post(INDIAPOST_PORTAL_URL, data=payload, timeout=15)
            if post_resp.status_code != 200:
                logger.error(f"POST query returned HTTP {post_resp.status_code}")
                return None

            # Step 4: Parse HTML result
            parsed = parse_indiapost_html(post_resp.text)

            if not parsed.get("events") and not parsed.get("booked_at"):
                # No data in table
                return None

            return TrackingResponse(
                success=True,
                consignment_number=consignment_no,
                status=parsed["status"],
                current_status=parsed["current_status"],
                delivered=parsed["delivered"],
                article_type=parsed["article_type"],
                booked_at=parsed["booked_at"],
                booked_on=parsed["booked_on"],
                destination=parsed["destination"],
                destination_pincode=parsed["destination_pincode"],
                delivered_at=parsed["delivered_at"],
                events_count=parsed["events_count"],
                events=parsed["events"],
                source="indiapost_portal_scraper"
            )

        except Exception as e:
            logger.error(f"Error scraping India Post portal: {e}")
            return None

    def _track_via_cept_api(self, consignment_no: str) -> Optional[TrackingResponse]:
        """
        Official CEPT Customer API (if credentials set in .env)
        """
        username = os.getenv("INDIAPOST_USERNAME")
        password = os.getenv("INDIAPOST_PASSWORD")
        base_url = os.getenv("INDIAPOST_BASE_URL", "https://corporate.cept.gov.in").rstrip("/")

        if not username or not password:
            return None

        try:
            # Login
            login_url = f"{base_url}/beextcustomer/v1/access/login"
            login_res = requests.post(login_url, json={"username": username, "password": password}, timeout=10)
            if login_res.status_code != 200:
                return None

            token_data = login_res.json()
            token = token_data.get("data", {}).get("access_token")
            if not token:
                return None

            # Bulk track endpoint
            track_url = f"{base_url}/beextcustomer/v1/tracking/bulk"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            track_res = requests.post(track_url, headers=headers, json={"bulk": [consignment_no]}, timeout=15)
            if track_res.status_code != 200:
                return None

            data = track_res.json()
            items = data.get("data", [])
            if not items:
                return None

            item = items[0]
            booking = item.get("booking_details", {})
            delivery = item.get("delivery_details", {})
            events_raw = item.get("event_details", [])

            events = []
            for ev in events_raw:
                events.append(TrackingEvent(
                    date=ev.get("event_date"),
                    time=ev.get("event_time"),
                    office=ev.get("event_office"),
                    event=ev.get("event_description"),
                    event_type=ev.get("event_code"),
                ))

            status = "delivered" if delivery.get("status", "").lower() == "delivered" else "in_transit"

            return TrackingResponse(
                success=True,
                consignment_number=consignment_no,
                status=status,
                current_status=delivery.get("status") or (events[0].event if events else "In Transit"),
                delivered=status == "delivered",
                article_type=booking.get("article_type", "Speed Post"),
                booked_at=booking.get("origin_office"),
                booked_on=booking.get("booking_date"),
                destination=booking.get("destination_office"),
                destination_pincode=booking.get("destination_pincode"),
                delivered_at=delivery.get("delivery_date"),
                events_count=len(events),
                events=events,
                source="official_cept_api"
            )

        except Exception as e:
            logger.error(f"Error querying CEPT API: {e}")
            return None


# Global instance
tracker_service = IndiaPostTrackerService()
