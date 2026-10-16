import re
import os
import time
import json
import base64
import logging
from typing import Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from cachetools import TTLCache

from app.models.schemas import TrackingResponse, TrackingEvent
from app.services.captcha_solver import solve_image_captcha, solve_text_captcha
from app.services.parser import parse_indiapost_json, parse_indiapost_html, determine_event_status

logger = logging.getLogger("indiapost_tracker")

INDIAPOST_BASE_URL = "https://www.indiapost.gov.in"
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "900"))  # 15 minutes


class IndiaPostTrackerService:
    def __init__(self):
        # Cache up to 1000 items with TTL
        self.cache = TTLCache(maxsize=1000, ttl=CACHE_TTL)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/x-component",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": INDIAPOST_BASE_URL,
            "Referer": f"{INDIAPOST_BASE_URL}/"
        }
        # Next.js Server Action IDs (auto-updated dynamically if they ever change)
        self.action_ids = {
            "apiHandlerForCaptcha": os.getenv("ACTION_CAPTCHA", "7f3ab4e2b026889d6719afd3e6916cf5224dcf9fe1"),
            "getTrackingToken": os.getenv("ACTION_TOKEN", "00b4f44fd7cd8e5a9d969100904e4880581555ea21"),
            "trackArticleWithCaptcha": os.getenv("ACTION_TRACK", "70bc3136e27b6f2d8159c7da34c65ac761901c1b12"),
        }
        self.last_action_discovery = 0

    def discover_action_ids(self, session: Optional[requests.Session] = None) -> bool:
        """
        Dynamically discovers Server Action IDs from the Next.js chunks if hashes update.
        """
        now = time.time()
        # Rate limit discovery to once every 10 minutes
        if now - self.last_action_discovery < 600:
            return False

        self.last_action_discovery = now
        sess = session or requests.Session()
        sess.headers.update({"User-Agent": self.headers["User-Agent"]})

        try:
            logger.info("Discovering Next.js Server Action IDs from indiapost.gov.in...")
            r = sess.get(INDIAPOST_BASE_URL, timeout=12)
            if r.status_code != 200:
                return False

            soup = BeautifulSoup(r.text, "html.parser")
            found = {}
            for s in soup.find_all("script"):
                src = s.get("src")
                if src and src.startswith("/_next/static/chunks/"):
                    chunk_url = INDIAPOST_BASE_URL + src
                    chunk_resp = sess.get(chunk_url, timeout=8)
                    if chunk_resp.status_code == 200:
                        txt = chunk_resp.text
                        for m in re.finditer(r'createServerReference\([\"\']([a-f0-9]+)[\"\'][^,]*?,[^,]*?,[^,]*?,[\"\']([^\"]+)[\"\']', txt):
                            name = m.group(2)
                            action_id = m.group(1)
                            if name in self.action_ids:
                                found[name] = action_id

            if found:
                self.action_ids.update(found)
                logger.info(f"Updated action IDs: {self.action_ids}")
                return True
        except Exception as e:
            logger.warning(f"Failed to auto-discover action IDs: {e}")

        return False

    def track(self, consignment_no: str) -> TrackingResponse:
        consignment_no = (consignment_no or "").strip().upper()

        # Validate standard 13-character India Post format (e.g., EE123456789IN, CR217442762IN)
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
            return self.cache[consignment_no]

        # Attempt 1: Next.js Portal Scraper (Current official India Post backend)
        result = self._track_via_nextjs_portal(consignment_no)
        if result and result.success:
            self.cache[consignment_no] = result
            return result

        # Attempt 2: Official CEPT API (if credentials configured in .env)
        cept_result = self._track_via_cept_api(consignment_no)
        if cept_result and cept_result.success:
            self.cache[consignment_no] = cept_result
            return cept_result

        # Attempt 3: Legacy ASP.NET WebForms portal fallback
        legacy_result = self._track_via_portal_legacy(consignment_no)
        if legacy_result and legacy_result.success:
            self.cache[consignment_no] = legacy_result
            return legacy_result

        # Return failure response
        err_msg = result.error if (result and result.error) else "Consignment details not available or portal temporarily unreachable"
        return TrackingResponse(
            success=False,
            consignment_number=consignment_no,
            status="pending",
            error=err_msg
        )

    def _track_via_nextjs_portal(self, consignment_no: str) -> Optional[TrackingResponse]:
        """
        Tracks consignment via India Post's Next.js App Router Server Actions.
        """
        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            session = requests.Session()
            session.headers.update(self.headers)

            try:
                # Step 1: Request image captcha
                captcha_action = self.action_ids.get("apiHandlerForCaptcha")
                captcha_headers = {**self.headers, "Next-Action": captcha_action}
                captcha_args = ["BASE_URL_BACKEND_CAPTCHA", "GET", None, "/captcha_generator?captcha_type=image"]

                r_captcha = session.post(
                    f"{INDIAPOST_BASE_URL}/",
                    headers=captcha_headers,
                    data=json.dumps(captcha_args),
                    timeout=15
                )

                # Check if action hash changed
                if r_captcha.status_code == 404 or "x-action-redirect" in r_captcha.headers:
                    logger.warning("Captcha action returned 404, attempting dynamic discovery...")
                    if self.discover_action_ids(session):
                        captcha_action = self.action_ids.get("apiHandlerForCaptcha")
                        captcha_headers["Next-Action"] = captcha_action
                        r_captcha = session.post(
                            f"{INDIAPOST_BASE_URL}/",
                            headers=captcha_headers,
                            data=json.dumps(captcha_args),
                            timeout=15
                        )

                if r_captcha.status_code != 200:
                    logger.warning(f"[Attempt {attempt}] Captcha request failed with status {r_captcha.status_code}")
                    continue

                # Parse Captcha ID and base64 image
                m_id = re.search(r'\"captcha_id1\":\s*\"([^\"]+)\"', r_captcha.text)
                if not m_id:
                    logger.warning(f"[Attempt {attempt}] Failed to find captcha_id1 in response")
                    continue
                captcha_id = m_id.group(1)

                m_img = re.search(r'data:image/jpeg;base64,([A-Za-z0-9+/=]+)', r_captcha.text)
                if not m_img:
                    logger.warning(f"[Attempt {attempt}] Failed to find captcha image base64 in response")
                    continue

                b64_str = m_img.group(1)
                rem = len(b64_str) % 4
                if rem:
                    b64_str = b64_str[:-rem]
                img_bytes = base64.b64decode(b64_str)

                # Step 2: Solve Captcha
                solved_answer = solve_image_captcha(img_bytes)
                if not solved_answer:
                    logger.warning(f"[Attempt {attempt}] Could not solve image captcha")
                    continue

                logger.info(f"[Attempt {attempt}] Captcha {captcha_id} solved as: '{solved_answer}'")

                # Step 3: Get tracking token
                token_action = self.action_ids.get("getTrackingToken")
                token_headers = {**self.headers, "Next-Action": token_action}

                r_token = session.post(
                    f"{INDIAPOST_BASE_URL}/",
                    headers=token_headers,
                    data=json.dumps([]),
                    timeout=15
                )

                token = None
                for line in r_token.text.split('\n'):
                    if line.startswith('1:'):
                        try:
                            token = json.loads(line[2:])
                        except Exception:
                            token = line[2:].strip().strip('"')
                        break

                if not token:
                    logger.warning(f"[Attempt {attempt}] Failed to obtain tracking token")
                    continue

                # Step 4: Track article with captcha
                track_action = self.action_ids.get("trackArticleWithCaptcha")
                track_headers = {**self.headers, "Next-Action": track_action}
                track_payload = [token, consignment_no, {"captchaId": captcha_id, "answer": solved_answer}]

                r_track = session.post(
                    f"{INDIAPOST_BASE_URL}/",
                    headers=track_headers,
                    data=json.dumps(track_payload),
                    timeout=20
                )

                if r_track.status_code != 200:
                    logger.warning(f"[Attempt {attempt}] Track query returned HTTP {r_track.status_code}")
                    continue

                track_json = None
                for line in r_track.text.split('\n'):
                    if line.startswith('1:'):
                        try:
                            track_json = json.loads(line[2:])
                        except Exception as e:
                            logger.error(f"Failed to parse track JSON line: {e}")
                        break

                if not track_json:
                    continue

                # If captcha failed on this attempt, retry
                if track_json.get("error") in ["captcha_failed", "captcha_required"]:
                    logger.warning(f"[Attempt {attempt}] Captcha rejected by India Post portal, retrying with new captcha...")
                    time.sleep(0.5)
                    continue

                if not track_json.get("success"):
                    msg = track_json.get("message") or track_json.get("error") or "Consignment not found"
                    last_error = msg
                    logger.info(f"India Post portal response for {consignment_no}: {msg}")
                    return TrackingResponse(
                        success=False,
                        consignment_number=consignment_no,
                        status="pending",
                        error=msg
                    )

                # Parse successful response
                data = track_json.get("data")
                parsed_response = parse_indiapost_json(data, consignment_no)
                if parsed_response:
                    return parsed_response
                else:
                    return TrackingResponse(
                        success=False,
                        consignment_number=consignment_no,
                        status="not_found",
                        error="Consignment details not found in India Post records"
                    )

            except Exception as e:
                logger.error(f"[Attempt {attempt}] Error scraping Next.js portal: {e}")
                last_error = str(e)
                time.sleep(0.5)

        logger.error(f"All {max_retries} Next.js tracking attempts failed for {consignment_no}. Last error: {last_error}")
        return None

    def _track_via_portal_legacy(self, consignment_no: str) -> Optional[TrackingResponse]:
        """
        Legacy scraper for the older ASP.NET WebForms portal.
        """
        portal_url = f"{INDIAPOST_BASE_URL}/_layouts/15/dop.portal.tracking/trackconsignment.aspx"
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.headers["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        })

        try:
            resp = session.get(portal_url, timeout=10)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            viewstate = soup.find("input", {"id": "__VIEWSTATE"})
            if not viewstate:
                return None

            viewstate_val = viewstate.get("value", "")
            viewstategen = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
            viewstategen_val = viewstategen.get("value", "") if viewstategen else ""
            eventvalidation = soup.find("input", {"id": "__EVENTVALIDATION"})
            eventvalidation_val = eventvalidation.get("value", "") if eventvalidation else ""

            captcha_ans = None
            captcha_lbl = soup.find("span", {"id": re.compile(r"lblCaptcha|Captcha|ucOERControl", re.I)})
            if captcha_lbl:
                captcha_ans = solve_text_captcha(captcha_lbl.get_text())

            if not captcha_ans:
                img_elem = soup.find("img", {"id": re.compile(r"imgCaptcha|Captcha", re.I)})
                if img_elem and img_elem.get("src"):
                    src = img_elem.get("src")
                    if src.startswith("data:image"):
                        b64_data = src.split(",", 1)[1]
                        captcha_ans = solve_image_captcha(base64.b64decode(b64_data))
                    else:
                        img_url = requests.compat.urljoin(portal_url, src)
                        img_resp = session.get(img_url, timeout=6)
                        if img_resp.status_code == 200:
                            captcha_ans = solve_image_captcha(img_resp.content)

            if not captcha_ans:
                return None

            payload = {
                "__VIEWSTATE": viewstate_val,
                "__VIEWSTATEGENERATOR": viewstategen_val,
                "__EVENTVALIDATION": eventvalidation_val,
                "ctl00$PlaceHolderMain$ucOERControl$txtSearch": consignment_no,
                "ctl00$PlaceHolderMain$ucOERControl$txtCaptcha": captcha_ans,
                "ctl00$PlaceHolderMain$ucOERControl$btnSearch": "Track Now"
            }

            post_resp = session.post(portal_url, data=payload, timeout=15)
            if post_resp.status_code != 200:
                return None

            parsed = parse_indiapost_html(post_resp.text)
            if not parsed.get("events") and not parsed.get("booked_at"):
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
                source="indiapost_legacy_portal_scraper"
            )
        except Exception as e:
            logger.debug(f"Legacy portal scraper error: {e}")
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
            login_url = f"{base_url}/beextcustomer/v1/access/login"
            login_res = requests.post(login_url, json={"username": username, "password": password}, timeout=10)
            if login_res.status_code != 200:
                return None

            token_data = login_res.json()
            token = token_data.get("data", {}).get("access_token")
            if not token:
                return None

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
                desc = ev.get("event_description")
                code = ev.get("event_code")
                events.append(TrackingEvent(
                    date=ev.get("event_date"),
                    time=ev.get("event_time"),
                    office=ev.get("event_office"),
                    event=desc,
                    event_type=code,
                    status=determine_event_status(desc, code)
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
                events=list(reversed(events)),
                source="official_cept_api"
            )

        except Exception as e:
            logger.error(f"Error querying CEPT API: {e}")
            return None


# Global instance
tracker_service = IndiaPostTrackerService()
