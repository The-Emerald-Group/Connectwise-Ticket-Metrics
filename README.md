# ConnectWise Ticket Stats

A self-hosted dashboard showing ticket **created** and **closed** counts per user over the last N days, with:

- **KPI summary bar** — total created, closed, net change, active users
- **Daily trend chart** — bar chart of created vs closed per day
- **Per-user cards** — created/closed/net per technician with board breakdown
- **Auto-refreshes** on a configurable interval (default: 5 minutes)

---

## Quick Start

### Docker Compose (recommended)

1. Edit `docker-compose.yml` with your ConnectWise credentials
2. Run:
```bash
docker compose up -d
```
3. Open http://localhost:5001

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `CW_SITE` | ConnectWise API hostname | `api-eu.myconnectwise.net` |
| `CW_COMPANY` | Company login ID | *(required)* |
| `CW_PUBLIC_KEY` | API public key | *(required)* |
| `CW_PRIVATE_KEY` | API private key | *(required)* |
| `CW_CLIENT_ID` | Developer client ID | *(required)* |
| `CW_VERIFY_SSL` | Verify SSL certificates | `true` |
| `HTTPS_PROXY` | Proxy URL if required | *(none)* |
| `CW_REFRESH_INTERVAL` | Auto-refresh in seconds | `300` |
| `CW_DAYS_BACK` | How many days to report on | `7` |

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard UI |
| `GET /api/ticket-stats` | Created/closed counts per user (JSON) |
| `GET /api/config-check` | Verify environment config (JSON) |
