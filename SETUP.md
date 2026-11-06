# Setup and demo guide

## Requirements

- Python 3.11 or newer (tested on 3.13)
- Node.js 20 or newer (tested on 24)
- A modern browser, and internet access for the map background

No API keys or paid services are needed.

## Run it

From the project root:

**Windows (PowerShell)**

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

**macOS or Linux**

```bash
./start.sh
```

The first run installs dependencies and builds the frontend, which takes a few minutes. Then open <http://127.0.0.1:8000>.

| Dashboard | Address |
| --- | --- |
| Start page | <http://127.0.0.1:8000> |
| Operator console | <http://127.0.0.1:8000/operator> |
| Passenger app | <http://127.0.0.1:8000/app> |
| API documentation | <http://127.0.0.1:8000/docs> |

The database is created and filled with the scenario automatically. If you change frontend code, delete `frontend/dist` so the launcher rebuilds it, or use development mode.

## Demo accounts

Every account uses the password `demo1234`.

| Role | Email | Notes |
| --- | --- | --- |
| Operator | `operator@stranded.demo` | Or press *Use demo operator* |
| Community driver | `meera@stranded.demo` | 12 completed rides |
| Community driver | `arjun@stranded.demo` | 3 completed rides |
| Passenger | `asha@stranded.demo` | P-01, party of 2 |
| Passenger | `vikram@stranded.demo` | P-02, travels alone |
| Passenger | `lakshmi@stranded.demo` | P-05, party of 4 |
| Passenger | `george@stranded.demo` | P-10, wheelchair user |

The passenger sign-in page lists every account as a one-click button.

**Each browser tab keeps its own sign-in**, so you can have the operator and several passengers open at once. A new tab always starts signed out.

## Judge stress-test controls

The bar at the top of the operator console runs every scenario in one click. It's open on the Overview and folds away on other pages. The KPI strip always stays visible.

| Control | What happens | Expected result |
|---|---|---|
| **Load Baseline Scenario** | Clean reset, X5 cancelled, simulated preferences | 24 stranded, 20 seats |
| **Crisis Surge** | Clean reset, demand x3, RV-2 withdrawn, RV-1 cut to 5 seats | 72 stranded, 10 seats |
| **Run Smart Allocation** | Runs the engine and reserves every proposal | Baseline 20 seated, 4 roll over. Surge 10 seated, 62 roll over in pools of 18, 16, 15 and 13 |
| **Simulate Community Carpool Wave** | Simulated drivers offer seats through the real matcher | Every rollover passenger gets a proposal. Nothing is confirmed |
| **Simulate Mutual Consent** | Passengers accept, then simulated drivers confirm | Rollover shows as confirmed by consent |

Telemetry faults (Vehicle A is RV-1, Vehicle B is RV-2, Vehicle C is RV-3):

| Fault | What to show |
|---|---|
| **Seat Spike** | Rejected and logged. The database seat count doesn't move |
| **Repeated Packet Storm** | 14 of 15 frames dropped, as one line in the *Audit log* |
| **Missing GPS Feed** | RV-3 turns amber and keeps moving on the *Disruption map* as an estimate. **Restore GPS** brings it back |
| **Conflicting Sensor Drop** | Run allocation first. RV-1 is quarantined with its bookings untouched, until you choose **Verified running** or **Confirm offline** |

A preset always starts clean so its numbers are reproducible, so it replaces any demo in progress, including accounts created during it.

## Running the demonstration

Takes about five minutes. Use one tab per person.

**Tab 1: operator.** Open `/operator` and press *Use demo operator*. The Overview shows a normal network, and the *Demonstration guide* on the right tracks your progress.

1. **Trigger the cancellation.** Go to *Disruption simulation* and press **Cancel the X5**. 24 passengers are affected.
2. **See the grouping.** Open *Grouping*. Parties are grouped only if they really travel the same way at the same time.

**Tab 2: passenger.** Open `/login` and choose **Asha**.

3. She sees that her service is disrupted. Press **Compare my options**, set a 1st and 2nd choice, and press **Send my choices**. The app says clearly that this isn't a booking.

**Tab 1: operator.**

4. Open *Preferences*. Asha's choices are already there, with no refresh needed.
5. Go to *Disruption simulation* and press **Simulate passenger responses** to stand in for everyone else. Back in *Preferences*, you can see availability, demand per option, and who hasn't responded.
6. Open *Smart allocation* and press **Run engine**. Compare the engine with first-come in the summary, and read why each unplaced party missed out.
7. Press **Approve and reserve all**. All 20 seats are reserved and none are overbooked.
8. Open *Explanations* and select **P-10** to walk through the score and feasibility checks.
9. Open *Heat map* and set *Allocation status* to **Unresolved only**. Click a grid cell to inspect it. Try *View: Where passengers are going*.

**Tab 3: community driver.** Open `/login` and choose **Meera Krishnan**.

10. Open *Carpool*. The listing shows about 4 people waiting at Hebbal for Whitefield, with no names.
11. On that listing press **I'm heading this way**, set *Leaving at* to `18:10`, set *Spare seats* to `4`, tick the declaration, and press **Offer my seats**. A match is proposed. Nothing is confirmed yet.

**Tab 2: Asha.**

12. Open *My journey* and press **Accept this ride**. The driver's identity stays hidden.

**Tabs 4 and 5: passengers.** Open `/login` as **Vikram**, then as **Harish**, and press **Accept this ride** in each.

**Tab 3: Meera.**

13. Open *My journey* and press **Confirm this ride**. Contact details appear for those involved, and only them.

**Tab 1: operator.** The Overview now shows 20 official, 4 carpool and 0 unresolved. See *Community carpool* and *Audit log* for the full trail.

### Optional: show recovery from a second failure

In *Vehicles*, press **Withdraw from service** on RV-2. Its confirmed passengers aren't silently moved. They appear under *Unresolved demand* as needing a decision, and each is told. Sign in as **Priya** to see the passenger's view.

You can also click a road on the *Disruption map* to close it. Vehicles divert, arrival times update, and any journey that now misses its deadline is flagged.

### Starting again

*Disruption simulation* → **Reset scenario**. Open passenger tabs stay signed in, unless the account was created during the demo.

## Development mode

Run these in two terminals for hot reloading.

```powershell
# Terminal 1: API on port 8000
cd backend
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend on port 5173, proxying /api and the WebSocket
cd frontend
npm run dev
```

Then open <http://localhost:5173>. On macOS or Linux, use `.venv/bin/python`.

## Running the tests

```powershell
cd backend
.venv\Scripts\python -m pytest
```

Tests use a temporary database and never touch the demo data. `python scripts/scenario_check.py` prints the scenario's outcome directly from the engines.

## Configuration

Everything has a working default. To change a setting, copy `backend/.env.example` to `backend/.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./stranded.db` | Database connection |
| `JWT_SECRET` | Development value | Signs sessions. Required when `DEMO_MODE=false` |
| `DEMO_MODE` | `true` | Enables reset, simulated responses and quick login |
| `ALLOCATION_SOLVER` | `auto` | `auto`, `cp_sat` or `greedy` |
| `CORS_ORIGINS` | Vite dev server | Allowed browser origins |

## Troubleshooting

| Problem | Fix |
| --- | --- |
| The map background is blank | Tile loading needs internet. Overlays and the heat layer still work. |
| Port 8000 is in use | Stop the other process, or edit the port in the start script. |
| Scripts are blocked on Windows | Use the exact `powershell -ExecutionPolicy Bypass -File start.ps1` command. |
| You're signed out in a new tab | Expected, as each tab holds its own sign-in. |
| Data looks wrong after experimenting | Use **Reset scenario**, or stop the server and delete `backend/stranded.db`. |
