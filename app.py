import os
import requests
import base64
import urllib3
from flask import Flask, jsonify, render_template
from datetime import datetime, timedelta, timezone
from collections import defaultdict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Changed template_folder to "." so it looks in the same directory for index.html
app = Flask(__name__, template_folder=".")

CW_SITE        = os.environ.get("CW_SITE", "api-eu.myconnectwise.net")
CW_COMPANY     = os.environ.get("CW_COMPANY", "")
CW_PUBLIC_KEY  = os.environ.get("CW_PUBLIC_KEY", "")
CW_PRIVATE_KEY = os.environ.get("CW_PRIVATE_KEY", "")
CW_CLIENT_ID   = os.environ.get("CW_CLIENT_ID", "")
HTTPS_PROXY    = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
REFRESH_INTERVAL = int(os.environ.get("CW_REFRESH_INTERVAL", "300"))
VERIFY_SSL     = os.environ.get("CW_VERIFY_SSL", "true").lower() != "false"
DAYS_BACK      = int(os.environ.get("CW_DAYS_BACK", "7"))

def get_session():
    s = requests.Session()
    if HTTPS_PROXY:
        s.proxies = {"https": HTTPS_PROXY, "http": HTTPS_PROXY}
    s.verify = VERIFY_SSL
    return s

def get_auth_header():
    creds = f"{CW_COMPANY}+{CW_PUBLIC_KEY}:{CW_PRIVATE_KEY}"
    encoded = base64.b64encode(creds.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "clientId": CW_CLIENT_ID,
        "Content-Type": "application/json"
    }

def cw_get(endpoint, params=None):
    url = f"https://{CW_SITE}/v4_6_release/apis/3.0{endpoint}"
    headers = get_auth_header()
    all_results = []
    page = 1
    page_size = 100

    if params is None:
        params = {}

    session = get_session()

    while True:
        paged_params = {**params, "page": page, "pageSize": page_size}
        response = session.get(url, headers=headers, params=paged_params, timeout=90)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        all_results.extend(data)
        if len(data) < page_size:
            break
        page += 1

    return all_results


@app.route("/")
def index():
    return render_template("index.html", refresh_interval=REFRESH_INTERVAL, days_back=DAYS_BACK)


@app.route("/api/ticket-stats")
def ticket_stats():
    try:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=DAYS_BACK)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        # --- Fetch created tickets in window ---
        created_params = {
            "conditions": f"dateEntered >= [{since_str}] and parentTicketId = null",
            "fields": "id,summary,owner,board,dateEntered",
            "orderBy": "dateEntered asc"
        }
        created_tickets = cw_get("/service/tickets", created_params)

        # --- Fetch closed/resolved tickets in window ---
        closed_params = {
            "conditions": f"closedFlag = true and lastUpdated >= [{since_str}] and parentTicketId = null",
            "fields": "id,summary,owner,board,lastUpdated,closedDate",
            "orderBy": "lastUpdated asc"
        }
        closed_tickets = cw_get("/service/tickets", closed_params)

        # --- Build daily buckets (Changed to use Day Names like "Monday") ---
        daily_buckets = {}
        for i in range(DAYS_BACK):
            day_dt = since + timedelta(days=i)
            day_key_str = day_dt.strftime("%Y-%m-%d") # Hidden key for sorting
            day_name = day_dt.strftime("%A")          # Visible name (e.g., Monday)
            daily_buckets[day_key_str] = {"date": day_name, "created": 0, "closed": 0}

        def get_day_key(iso):
            try:
                return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except:
                return None

        for t in created_tickets:
            k = get_day_key(t.get("dateEntered", ""))
            if k and k in daily_buckets:
                daily_buckets[k]["created"] += 1

        for t in closed_tickets:
            ts = t.get("closedDate") or t.get("lastUpdated", "")
            k = get_day_key(ts)
            if k and k in daily_buckets:
                daily_buckets[k]["closed"] += 1

        # --- Per-user aggregation ---
        user_created = defaultdict(list)
        user_closed  = defaultdict(list)

        def get_owner(t):
            o = t.get("owner")
            if isinstance(o, dict):
                return o.get("name", "Unassigned")
            return o or "Unassigned"

        def get_board(t):
            b = t.get("board")
            if isinstance(b, dict):
                return b.get("name", "")
            return b or ""

        for t in created_tickets:
            user_created[get_owner(t)].append(get_board(t))

        for t in closed_tickets:
            user_closed[get_owner(t)].append(get_board(t))

        all_users = set(user_created.keys()) | set(user_closed.keys())

        users_result = []
        for name in sorted(all_users):
            created_boards = user_created[name]
            closed_boards  = user_closed[name]

            board_names = set(created_boards) | set(closed_boards)
            boards = []
            for bn in sorted(board_names):
                if not bn:
                    continue
                boards.append({
                    "name": bn,
                    "created": created_boards.count(bn),
                    "closed": closed_boards.count(bn)
                })
            boards.sort(key=lambda x: x["created"] + x["closed"], reverse=True)

            users_result.append({
                "name": name,
                "created": len(created_boards),
                "closed": len(closed_boards),
                "boards": boards
            })

        users_result.sort(key=lambda u: u["created"] + u["closed"], reverse=True)

        return jsonify({
            "totals": {
                "created": len(created_tickets),
                "closed": len(closed_tickets)
            },
            "users": users_result,
            "daily": list(daily_buckets.values()),
            "asOf": now.isoformat(),
            "daysBack": DAYS_BACK
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config-check")
def config_check():
    configured = all([CW_COMPANY, CW_PUBLIC_KEY, CW_PRIVATE_KEY, CW_CLIENT_ID])
    return jsonify({
        "configured": configured,
        "site": CW_SITE,
        "company": CW_COMPANY if CW_COMPANY else "(not set)",
        "hasPublicKey": bool(CW_PUBLIC_KEY),
        "hasPrivateKey": bool(CW_PRIVATE_KEY),
        "hasClientId": bool(CW_CLIENT_ID),
        "proxy": HTTPS_PROXY if HTTPS_PROXY else "none",
        "sslVerify": VERIFY_SSL
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
