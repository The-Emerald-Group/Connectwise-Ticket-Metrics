import os
import requests
import base64
import urllib3
from flask import Flask, jsonify, render_template_string
from datetime import datetime, timedelta, timezone
from collections import defaultdict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

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


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ConnectWise Ticket Stats</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {
    --green: #4cd964;
    --red: #ff3b30;
    --blue: #0a84ff;
    --amber: #ffcc00;
    --purple: #bf5af2;
    --bg: #0a0a0a;
    --card-bg: #161616;
    --header-bg: #111111;
    --border: #222222;
    --text: #ffffff;
    --text-dim: #888888;
    --text-muted: #444444;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-height: 100vh; }
  
  header { background: var(--header-bg); border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
  .logo { font-size: 1rem; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: white; }
  .logo span { color: var(--green); }
  .header-right { display: flex; align-items: center; gap: 16px; }
  .refresh-status { display: flex; align-items: center; gap: 8px; font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }
  .pulse-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; flex-shrink: 0; }
  @keyframes pulse { 0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(76,217,100,0.5)}50%{opacity:.7;box-shadow:0 0 0 5px rgba(76,217,100,0)} }
  .countdown-ring { position: relative; width: 26px; height: 26px; flex-shrink: 0; }
  .countdown-ring svg { transform: rotate(-90deg); }
  .countdown-ring .bg { fill: none; stroke: #333; stroke-width: 2.5; }
  .countdown-ring .progress { fill: none; stroke: var(--green); stroke-width: 2.5; stroke-linecap: round; transition: stroke-dashoffset 1s linear; }
  .countdown-label { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); font-size: 8px; color: var(--green); font-weight: 700; }

  .config-warning { background: rgba(255,59,48,0.08); border-left: 4px solid var(--red); padding: 16px 24px; margin: 20px 24px; border-radius: 0 8px 8px 0; display: none; }
  .config-warning.visible { display: block; }
  .config-warning h3 { color: var(--red); font-size: .9rem; margin-bottom: 8px; }
  .config-warning p { font-size: .8rem; color: var(--text-dim); line-height: 1.8; }
  .config-warning code { background: rgba(255,255,255,.07); padding: 1px 6px; border-radius: 3px; color: var(--amber); }

  main { padding: 24px; }

  /* Summary KPI bar */
  .kpi-bar { display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }
  .kpi-card { flex: 1; min-width: 160px; background: var(--card-bg); border-radius: 12px; padding: 18px 20px; border-top: 3px solid; }
  .kpi-card.created { border-color: var(--blue); }
  .kpi-card.closed  { border-color: var(--green); }
  .kpi-card.delta   { border-color: var(--amber); }
  .kpi-card.users   { border-color: var(--purple); }
  .kpi-label { font-size: .7rem; text-transform: uppercase; letter-spacing: 1.5px; color: var(--text-dim); margin-bottom: 8px; }
  .kpi-value { font-size: 2.2rem; font-weight: 800; line-height: 1; }
  .kpi-value.created { color: var(--blue); }
  .kpi-value.closed  { color: var(--green); }
  .kpi-value.delta.positive { color: var(--red); }
  .kpi-value.delta.negative { color: var(--green); }
  .kpi-value.delta.neutral  { color: var(--text-dim); }
  .kpi-value.users { color: var(--purple); }
  .kpi-sub { font-size: .72rem; color: var(--text-muted); margin-top: 4px; }

  .section-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
  .section-title { font-size: .8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; color: var(--text-dim); }
  .section-gap { margin-bottom: 40px; }

  /* User cards grid */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 20px; align-items: start; }
  .user-card { background: var(--card-bg); border-radius: 12px; padding: 20px; }
  .user-name { font-size: 1.1rem; font-weight: 700; margin-bottom: 12px; }
  .stat-row { display: flex; gap: 12px; margin-bottom: 14px; }
  .stat-box { flex: 1; border-radius: 8px; padding: 12px 14px; text-align: center; }
  .stat-box.created { background: rgba(10,132,255,0.1); border: 1px solid rgba(10,132,255,0.2); }
  .stat-box.closed  { background: rgba(76,217,100,0.1); border: 1px solid rgba(76,217,100,0.2); }
  .stat-box.net     { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); }
  .stat-box .val { font-size: 1.8rem; font-weight: 800; line-height: 1; margin-bottom: 2px; }
  .stat-box.created .val { color: var(--blue); }
  .stat-box.closed  .val { color: var(--green); }
  .stat-box.net .val.positive { color: var(--red); }
  .stat-box.net .val.negative { color: var(--green); }
  .stat-box.net .val.neutral  { color: var(--text-dim); }
  .stat-box .lbl { font-size: .65rem; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); }

  /* Board breakdown inside card */
  .board-breakdown { border-top: 1px solid var(--border); padding-top: 12px; }
  .board-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; font-size: .78rem; color: var(--text-dim); }
  .board-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 60%; }
  .board-pills { display: flex; gap: 6px; }
  .board-pill { font-size: .65rem; font-weight: 700; padding: 2px 8px; border-radius: 20px; }
  .board-pill.c { background: rgba(10,132,255,0.15); color: var(--blue); }
  .board-pill.x { background: rgba(76,217,100,0.15); color: var(--green); }

  /* Trend chart */
  .chart-container { background: var(--card-bg); border-radius: 12px; padding: 20px; }
  .chart-wrap { position: relative; height: 260px; }

  .loading { display: flex; align-items: center; justify-content: center; padding: 60px; color: var(--text-dim); gap: 12px; font-size: .8rem; }
  .spinner { width: 18px; height: 18px; border: 2px solid #333; border-top-color: var(--green); border-radius: 50%; animation: spin .8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error-msg { padding: 30px; color: var(--red); font-size: .8rem; }
</style>
</head>
<body>
<header>
  <div class="logo">ConnectWise <span>Ticket Stats</span></div>
  <div class="header-right">
    <div class="refresh-status">
      <div class="pulse-dot"></div>
      <span id="last-updated-label">Loading…</span>
      <div class="countdown-ring">
        <svg width="26" height="26" viewBox="0 0 26 26">
          <circle class="bg" cx="13" cy="13" r="10"/>
          <circle class="progress" id="countdown-circle" cx="13" cy="13" r="10" stroke-dasharray="62.8" stroke-dashoffset="0"/>
        </svg>
        <span class="countdown-label" id="countdown-text">...</span>
      </div>
    </div>
  </div>
</header>

<div class="config-warning" id="config-warning">
  <h3>⚠ ConnectWise API Not Configured</h3>
  <p>Set <code>CW_SITE</code>, <code>CW_COMPANY</code>, <code>CW_PUBLIC_KEY</code>, <code>CW_PRIVATE_KEY</code>, <code>CW_CLIENT_ID</code> in your docker-compose.yml.</p>
</div>

<main>
  <div id="main-content"><div class="loading"><div class="spinner"></div>Loading stats…</div></div>
</main>

<script>
const REFRESH_INTERVAL = parseInt('{{ refresh_interval }}') || 300;
const DAYS_BACK = parseInt('{{ days_back }}') || 7;
let countdown = REFRESH_INTERVAL;
const circle = document.getElementById('countdown-circle');
const circumference = 62.8;
let trendChart = null;

setInterval(() => {
  countdown--;
  if (countdown <= 0) { countdown = REFRESH_INTERVAL; loadStats(); }
  circle.style.strokeDashoffset = circumference * (1 - countdown / REFRESH_INTERVAL);
  const mins = Math.floor(countdown / 60);
  const secs = countdown % 60;
  document.getElementById('countdown-text').textContent = mins > 0 ? mins + 'm' : secs + 's';
}, 1000);

function netClass(n) {
  if (n > 0) return 'positive';
  if (n < 0) return 'negative';
  return 'neutral';
}
function netLabel(n) {
  if (n > 0) return `+${n}`;
  return `${n}`;
}

async function loadStats() {
  try {
    const res = await fetch('/api/ticket-stats');
    const data = await res.json();
    if (data.error) {
      document.getElementById('main-content').innerHTML = `<div class="error-msg">⚠ ${data.error}</div>`;
      return;
    }

    const now = new Date().toLocaleTimeString('en-GB', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
    document.getElementById('last-updated-label').textContent = `Updated ${now}`;

    const { totals, users, daily } = data;
    const netVal = totals.created - totals.closed;
    const netCls = netClass(netVal);

    // KPI bar
    const kpiHTML = `
      <div class="kpi-bar">
        <div class="kpi-card created">
          <div class="kpi-label">Tickets Created</div>
          <div class="kpi-value created">${totals.created}</div>
          <div class="kpi-sub">Last ${DAYS_BACK} days</div>
        </div>
        <div class="kpi-card closed">
          <div class="kpi-label">Tickets Closed</div>
          <div class="kpi-value closed">${totals.closed}</div>
          <div class="kpi-sub">Last ${DAYS_BACK} days</div>
        </div>
        <div class="kpi-card delta">
          <div class="kpi-label">Net Change</div>
          <div class="kpi-value delta ${netCls}">${netLabel(netVal)}</div>
          <div class="kpi-sub">${netVal > 0 ? 'Queue growing' : netVal < 0 ? 'Queue shrinking' : 'Balanced'}</div>
        </div>
        <div class="kpi-card users">
          <div class="kpi-label">Active Users</div>
          <div class="kpi-value users">${users.length}</div>
          <div class="kpi-sub">With activity</div>
        </div>
      </div>`;

    // Trend chart
    const trendHTML = `
      <div class="section-gap">
        <div class="section-header"><span class="section-title">Daily Trend — Last ${DAYS_BACK} Days</span></div>
        <div class="chart-container"><div class="chart-wrap"><canvas id="trendChart"></canvas></div></div>
      </div>`;

    // User cards
    const userCards = users.map(u => {
      const net = u.created - u.closed;
      const netC = netClass(net);
      const boardsHTML = u.boards.map(b => `
        <div class="board-row">
          <span class="board-name">${b.name}</span>
          <div class="board-pills">
            <span class="board-pill c">${b.created} created</span>
            <span class="board-pill x">${b.closed} closed</span>
          </div>
        </div>`).join('');

      return `<div class="user-card">
        <div class="user-name">${u.name}</div>
        <div class="stat-row">
          <div class="stat-box created"><div class="val">${u.created}</div><div class="lbl">Created</div></div>
          <div class="stat-box closed"><div class="val">${u.closed}</div><div class="lbl">Closed</div></div>
          <div class="stat-box net"><div class="val ${netC}">${netLabel(net)}</div><div class="lbl">Net</div></div>
        </div>
        ${u.boards.length ? `<div class="board-breakdown">${boardsHTML}</div>` : ''}
      </div>`;
    }).join('');

    document.getElementById('main-content').innerHTML = kpiHTML + trendHTML + `
      <div class="section-gap">
        <div class="section-header"><span class="section-title">Per User Breakdown</span></div>
        <div class="grid">${userCards || '<p style="color:var(--text-dim);font-size:.8rem">No activity found in this period.</p>'}</div>
      </div>`;

    // Render chart
    if (trendChart) { trendChart.destroy(); trendChart = null; }
    const ctx = document.getElementById('trendChart').getContext('2d');
    trendChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: daily.map(d => d.date),
        datasets: [
          { label: 'Created', data: daily.map(d => d.created), backgroundColor: 'rgba(10,132,255,0.6)', borderColor: 'rgba(10,132,255,0.9)', borderWidth: 1, borderRadius: 4 },
          { label: 'Closed',  data: daily.map(d => d.closed),  backgroundColor: 'rgba(76,217,100,0.6)', borderColor: 'rgba(76,217,100,0.9)', borderWidth: 1, borderRadius: 4 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#888', font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: '#888' }, grid: { color: '#1e1e1e' } },
          y: { ticks: { color: '#888' }, grid: { color: '#1e1e1e' }, beginAtZero: true }
        }
      }
    });

  } catch(e) {
    document.getElementById('main-content').innerHTML = `<div class="error-msg">⚠ ${e.message}</div>`;
  }
}

async function checkConfig() {
  try {
    const data = await fetch('/api/config-check').then(r => r.json());
    if (!data.configured) document.getElementById('config-warning').classList.add('visible');
  } catch(e) {}
}

checkConfig();
loadStats();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML, refresh_interval=REFRESH_INTERVAL, days_back=DAYS_BACK)


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
        # We query by lastUpdated in window AND closed status
        closed_statuses_query = "Closed,Resolved,Completed,Complete,Cancelled,Closed - Resolved,Closed - No Resolution"
        closed_conditions = " or ".join(
            [f'status/name = "{s.strip()}"' for s in closed_statuses_query.split(",")]
        )
        closed_params = {
            "conditions": f"closedFlag = true and lastUpdated >= [{since_str}] and parentTicketId = null",
            "fields": "id,summary,owner,board,lastUpdated,closedDate",
            "orderBy": "lastUpdated asc"
        }
        closed_tickets = cw_get("/service/tickets", closed_params)

        # --- Build daily buckets ---
        daily_buckets = {}
        for i in range(DAYS_BACK):
            day = (since + timedelta(days=i)).strftime("%d %b")
            daily_buckets[day] = {"date": day, "created": 0, "closed": 0}

        def day_key(iso):
            try:
                return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b")
            except:
                return None

        for t in created_tickets:
            k = day_key(t.get("dateEntered", ""))
            if k and k in daily_buckets:
                daily_buckets[k]["created"] += 1

        for t in closed_tickets:
            # Use closedDate if available, else lastUpdated
            ts = t.get("closedDate") or t.get("lastUpdated", "")
            k = day_key(ts)
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

            # Board breakdown
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

        # Sort users by total activity
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
