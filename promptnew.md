We are building "The Stranded Network" (a Dynamic Travel Recovery, Passenger Coordination & Community Carpooling Platform with a Passenger Dashboard, Operator Dashboard, Grouping Engine, Priority Allocation Engine, Operator Heat Map, Community Carpooling Fallback, and Audit Log).

We have just been given two hackathon stress-test constraints that our application must visibly handle and defend against:
1. CONSTRAINT 10 (Unreliable Telemetry): "Some incoming sensor or telemetry readings become unreliable. The injected feed may include missing readings, sudden spikes, repeated values, unusual fluctuations, delayed observations or conflicting readings from different sensors."
2. SURGE CONSTRAINT (3x Demand / -50% Resources): "Demand suddenly increases to three times the original level while the available resource pool is reduced by 50%."

Please inspect our existing codebase and implement the following architectural upgrades across our backend and frontend:

### PART A: Telemetry Sanitizer & Non-Destructive State Guard (Constraint 10)
1. **Telemetry Sanitizer Middleware / Service:**
   - Create a sanitization pipeline for incoming vehicle/route telemetry updates before they touch application state:
     - **Spike & Negative Clamping:** Cross-check incoming `available_seats` against the vehicle's static database `capacity`. If a sensor reports `available_seats > capacity` (e.g., 50 seats on an 8-seat bus) or `< 0`, reject the reading, keep the database atomic seat count as the source of truth, and log a `TELEMETRY_SPIKE_REJECTED` event in the Audit Log.
     - **Duplicate Packet Filtering:** Track a hash or `(vehicle_id, timestamp, payload_hash)` of the last telemetry packet. If an identical repeated packet arrives within 5 seconds, drop it silently or increment a deduplication counter.
     - **Missing / Delayed Observation Fallback (Dead-Reckoning):** If a vehicle telemetry ping is missing or delayed beyond threshold, mark the vehicle telemetry status as `STALE_DEAD_RECKONING` and retain its last verified coordinates/state rather than crashing or zeroing out the vehicle.
     - **Conflicting Sensor Quarantine (Non-Destructive Guarantee):** If one sensor reports a route/vehicle as blocked/offline while another reports it active—AND that vehicle already has `CONFIRMED` passenger allocations—do NOT silently cancel or overwrite the confirmed passenger seats. Instead, set a `telemetry_conflict_flag = True` (`STATUS: TELEMETRY_CONFLICT_PENDING_OPERATOR_REVIEW`) on the Operator Dashboard and create an Audit Log entry requiring manual operator confirmation.
2. **Operator UI Telemetry Indicators:**
   - On the Operator Dashboard vehicle cards and header, display a live **Telemetry Health Badge**:
     - Green: `Verified Feed`
     - Amber: `Stale Feed (Dead-Reckoning Active)`
     - Red: `Sensor Conflict Quarantined — DB Lock Enforced`
   - Ensure every rejected spike, deduplicated packet, or quarantined conflict immediately appears in the Operator **Audit Log** with a clear human-readable reason.

### PART B: 3x Demand & 50% Resource Cut Resilience
1. **Strict Atomic Capacity Lock:**
   - Ensure the Official Allocation Engine strictly enforces `allocated_seats <= available_seats` at the transaction level so `Over-Allocation Count` remains `0` even when 72 passengers compete for 10 seats.
2. **Hard Accessibility Gate + Weighted Triage:**
   - When available seats are cut by 50% (down to 10 seats across the fleet), ensure the allocation engine filters for accessibility suitability as a hard constraint first, then ranks groups using our weighted priority formula (`waiting_time`, `urgency`, `alternative_scarcity`, `group_integrity`, `preference_match`), and generates a clear explanation string for why the top 10 seats were awarded (e.g., `"Prioritised under 50% fleet reduction: Group G-01 has wheelchair requirement + highest urgency score (0.94)"`).
3. **Automatic Tier-2 Community Carpool Cascade:**
   - Automatically transition all remaining unallocated passengers (e.g., the 62 remaining passengers under the 3x surge) into `UNRESOLVED_DEMAND` and cluster them into aggregated, anonymised **Community Carpool Corridor Requests** (grouped by destination zone, pickup zone, and departure window).
   - Display a prominent **"Surge Carpool Mobilisation"** banner on both the Operator Dashboard and the Passenger/Carpool Provider view showing how many stranded passengers are pooled per corridor and allowing registered community drivers to offer spare seats and match with groups.



Now build an interactive "Judge Stress-Test & Simulation Control Bar" at the top of the Operator Dashboard (and synced with the Passenger Dashboard) so we can demonstrate our baseline scenario and both hackathon constraints live with single-click presets.

Please implement the following deterministic, reproducible simulation scenarios and controls:

### 1. Scenario Preset 1: "Load Baseline Scenario (24 Pax / 20 Seats)"
- Resets the database/state cleanly and seeds our baseline evening commute cancellation:
  - **24 affected passengers** clustered into compatible groups across multiple destinations, with varied wait times, urgency, ranked preferences (1st/2nd choice), and accessibility needs.
  - **3 official replacement vehicles:** Vehicle A (8 seats), Vehicle B (7 seats), Vehicle C (5 seats) = **20 total official seats**.
  - When "Run Smart Allocation" is clicked: 20 passengers are seated officially (0 over-allocations), and **4 passengers** roll over into a Community Carpool request where a demo carpool provider can offer 4 seats and complete the mutual-consent match.

### 2. Scenario Preset 2: "Trigger Constraint 2: Crisis Surge (3x Demand = 72 Pax / -50% Fleet = 10 Seats)"
- Can be triggered from scratch or dynamically on top of the active network:
  - **Scales affected demand 3x to 72 passengers** (clustered into realistic passenger groups across 4 major travel corridors).
  - **Cuts official replacement vehicle capacity by 50% to 10 total seats** (marks Vehicle B [7 seats] as unavailable/disabled and reduces Vehicle A from 8 to 5 usable seats, leaving Vehicle A [5 seats] + Vehicle C [5 seats] = 10 seats).
  - Updates the **Operator Heat Map** to show high-intensity red demand clusters across the affected pickup zones.
  - When "Run Smart Allocation" is clicked:
    - Strictly allocates exactly **10/10 official seats** to the highest-priority / accessibility-critical groups with full score breakdowns and zero overbooking (`Over-Allocation = 0`).
    - Automatically cascades the **62 unallocated passengers** into aggregated **Community Carpool Corridor Pools** (e.g., Corridor 1: 18 pax, Corridor 2: 16 pax, Corridor 3: 15 pax, Corridor 4: 13 pax).
  - Provide a **"Simulate Community Carpool Wave"** button that spawns multiple registered community drivers along those corridors offering spare seats so we can show the 62 passengers getting matched via mutual consent.

### 3. Scenario Preset 3: "Inject Constraint 10: Corrupted Telemetry Feed"
- Add a dedicated dropdown or button group for **Telemetry Chaos Injection** with 4 live fault buttons:
  1. **Inject Seat Spike (`+42 Phantom Seats`):** Sends a corrupted sensor payload claiming Vehicle A has 50 available seats instead of 8. Show the sanitizer clamping it, keeping the UI at true capacity, and logging `[REJECTED] Sensor spike: Vehicle A reported 50 seats (max 8). Enforcing DB Atomic Lock.`
  2. **Inject Repeated Packet Storm:** Sends 15 duplicate telemetry frames in 1 second. Show the deduplication counter incrementing without triggering redundant re-routing calculations.
  3. **Inject Missing / Delayed GPS Feed:** Stops GPS pings for Vehicle C. Show Vehicle C switching its badge to `STALE_DEAD_RECKONING` with interpolated position rather than disappearing from the map.
  4. **Inject Conflicting Sensor Drop on Confirmed Bus:** Sends a conflicting sensor reading claiming Vehicle A is offline *after* passengers are already confirmed on it. Show the system refusing to wipe the confirmed bookings (`NON-DESTRUCTIVE LOCK ACTIVE`), flagging the vehicle as `SENSOR_CONFLICT_QUARANTINED`, and prompting the operator in the Audit Log to verify or manually override.

### 4. Live KPI & Telemetry Banner
- Add a clean KPI strip at the top of the Operator Dashboard that updates in real time across all simulations:
  - `Stranded Passengers` (24 vs 72)
  - `Official Seats Available` (20 vs 10)
  - `Over-Allocation Count` (Always `0` — highlighted in green)
  - `Tier-2 Carpool Rollover` (4 vs 62)
  - `Telemetry Sanitizer Status` (Shows count of quarantined spikes/conflicts)