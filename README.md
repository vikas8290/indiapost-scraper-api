# 📮 India Post Free Self-Hosted Tracking API (Python)

A free, self-hosted, lightweight REST API microservice built with **FastAPI** to track **India Post (Speed Post / Registered Post)** parcels and consignments without paying for RapidAPI or third-party tracking subscriptions.

---

## 🚀 Features

- **100% Free & Unlimited:** No RapidAPI quota, no per-request fees, no credit card needed.
- **RESTful Endpoints:** Standard JSON responses compatible with any frontend or backend (Laravel, Node.js, Python, PHP, etc.).
- **Auto Captcha Solver:** Automatically solves mathematical and textual Captchas from the India Post tracking portal.
- **Interactive Swagger Docs:** Test tracking numbers directly in browser at `http://localhost:8000/docs`.
- **Built-in In-Memory Cache (TTL):** Prevents spamming the portal by caching results for 15 minutes.
- **Official CEPT Fallback Support:** If you have an official India Post business account, optionally configure credentials in `.env` for direct official CEPT bulk tracking.
- **Docker Ready:** Ships with `Dockerfile` and `docker-compose.yml`.

---

## 🛠️ Quick Start

### Option A: Using the Automatic Script (`run.sh`)
```bash
cd indiapost-scraper-api
./run.sh
```

### Option B: Manual Setup (Local Python)
```bash
cd indiapost-scraper-api

# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create environment file
cp .env.example .env

# 4. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option C: Using Docker
```bash
cd indiapost-scraper-api
docker compose up -d --build
```

The API will be live at **`http://localhost:8000`**.
Open **`http://localhost:8000/docs`** to see the interactive Swagger UI.

---

## 📡 API Endpoints

### 1. Track Consignment (GET by Path)
```http
GET /api/track/{consignment_number}
```
**Example:**
```bash
curl http://localhost:8000/api/track/EE123456789IN
```

### 2. Track Consignment (GET by Query)
```http
GET /api/track?consignment=EE123456789IN
```

### 3. Track Consignment (POST JSON Body)
```http
POST /api/track
Content-Type: application/json

{
  "consignment_number": "EE123456789IN"
}
```

### 4. Health Check
```http
GET /api/health
```

---

## 📄 Response Format

```json
{
  "success": true,
  "consignment_number": "EE123456789IN",
  "status": "delivered",
  "current_status": "Item Delivered to Addressee",
  "delivered": true,
  "article_type": "Speed Post",
  "booked_at": "Jaipur GPO",
  "booked_on": "10/10/2026 11:30:00",
  "destination": "New Delhi GPO",
  "destination_pincode": "110001",
  "delivered_at": "14/10/2026 14:15:00",
  "returned_at": null,
  "last_updated": null,
  "events_count": 5,
  "events": [
    {
      "date": "14/10/2026",
      "time": "14:15:00",
      "office": "New Delhi GPO",
      "event": "Item Delivered",
      "event_type": "item_delivered",
      "status": "delivered"
    },
    {
      "date": "14/10/2026",
      "time": "09:30:00",
      "office": "New Delhi GPO",
      "event": "Out for Delivery",
      "event_type": "out_for_delivery",
      "status": "out_for_delivery"
    },
    {
      "date": "12/10/2026",
      "time": "18:45:00",
      "office": "Delhi NSH",
      "event": "Item Dispatched",
      "event_type": "item_dispatched",
      "status": "in_transit"
    },
    {
      "date": "10/10/2026",
      "time": "11:30:00",
      "office": "Jaipur GPO",
      "event": "Item Booked",
      "event_type": "item_booked",
      "status": "booked"
    }
  ],
  "error": null,
  "source": "indiapost_portal_scraper"
}
```

---

## 🔗 How to Connect with Laravel Admin (`registaniachar-admin`)

In your Laravel project (`registaniachar-admin`), update `config/services.php`:
```php
'indiapost_api' => [
    'url' => env('INDIAPOST_API_URL', 'http://127.0.0.1:8000'),
],
```

And in `.env`:
```env
INDIAPOST_API_URL=http://127.0.0.1:8000
```

Now, `IndiaPostTracker.php` can simply call `GET /api/track/{consignment}` instead of RapidAPI!
