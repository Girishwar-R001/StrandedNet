# The Stranded Network

## Dynamic Travel Recovery, Passenger Coordination & Community Carpooling Platform

## 1. Project Overview

The Stranded Network is a transport-disruption recovery platform with
two separate interfaces:

-   **Passenger Dashboard:** helps travellers report affected journeys,
    compare and select alternatives, track allocations, and participate
    in community carpooling.
-   **Operator Dashboard:** helps transport operators monitor
    disruptions, group passengers, manage replacement capacity, review
    passenger preferences, allocate vehicles, and resolve unmet demand.

When a bus, train, shuttle, or route becomes unavailable, the platform
identifies affected passengers, groups compatible journeys, recommends
alternatives, and allocates official replacement transport fairly
without exceeding capacity.

If official replacement transport cannot accommodate everyone, the
platform provides a **community carpooling fallback**. Ordinary
registered users who are already travelling in a compatible direction
can offer spare seats to stranded passengers.

The operator dashboard also includes an **operator-only disruption heat
map**. Passengers can select preferred recovery options, and those
preferences appear on the operator dashboard to reduce manual
coordination.

**Core principle:** Treat a disruption as a shared
passenger-and-capacity coordination problem, not as hundreds of isolated
route-planning requests.

## 2. Problem Statement

Transport disruptions can strand large numbers of passengers at once.
Traditional journey-planning systems generally help individuals find
routes, but do not adequately coordinate groups of affected passengers
or allocate limited replacement capacity across them.

During a major disruption: - Passengers with similar destinations
independently search for alternatives. - Replacement vehicles may be
poorly utilised. - Limited seats may be allocated inconsistently. -
Operators may struggle to understand where demand is concentrated. -
Operators must manually contact passengers to understand their
preferences. - Some passengers remain stranded after official
replacement capacity is exhausted.

The Stranded Network addresses these issues through passenger grouping,
dynamic re-routing, capacity-aware allocation, passenger-selected
preferences, operator decision support, disruption visualisation, and
community carpooling.

## 3. Objectives

1.  Group passengers with compatible destinations, departure points,
    travel requirements, and time constraints.
2.  Recalculate feasible journeys after cancellations, delays, and route
    closures.
3.  Allocate official replacement vehicles and seats without
    over-allocation.
4.  Apply transparent, inspectable prioritisation rules.
5.  Recommend alternative journeys and allow passengers to select
    preferences.
6.  Give operators a live dashboard showing affected passengers,
    capacity, allocations, and unresolved demand.
7.  Visualise disruption intensity and affected passenger concentrations
    using an operator-only heat map.
8.  Offer a community carpooling fallback for passengers who cannot be
    accommodated by official replacement transport.
9.  Reduce operator workload by collecting passenger preferences and
    presenting consolidated recommendations.

## 4. User Roles and Separate Dashboards

### 4.1 Passenger Dashboard

A passenger should be able to: - Register or sign in. - Submit or
confirm an affected journey. - Enter current location, destination,
group size, preferred departure/arrival time, and travel requirements. -
View recommended alternative journeys. - Compare alternatives and select
or rank preferred options. - Track whether a preference is pending,
accepted, or confirmed. - View assigned replacement transport and pickup
details. - Join a suitable carpool request if official transport is
unavailable. - Offer a carpool if independently travelling to a
compatible destination with spare seats. - View carpool offers, proposed
matches, and status. - Receive disruption and journey updates.

Clearly distinguish: - Suggested journey - Passenger-selected
preference - Operator-approved allocation - Confirmed vehicle/seat
reservation - Community carpool offer - Confirmed carpool arrangement

A passenger selecting an option does **not** mean a seat has been
reserved.

### 4.2 Operator Dashboard

The operator dashboard is a separate, role-protected interface.
Operators should be able to: - Create and manage disruptions. - View
affected passengers and passenger groups. - Inspect passenger-selected
journey preferences. - Review grouping and allocation recommendations. -
Manage replacement vehicles and capacity. - Run or re-run allocation. -
Inspect prioritisation explanations. - View unresolved demand. - Monitor
community carpool activity and its status. - View the operator-only
disruption heat map. - Review audit logs and operator overrides.

Operators retain control over official transport allocations and manual
overrides.

### 4.3 Community Carpool Provider

An ordinary registered user may act as a carpool provider without being
a transport operator. They should be able to: - View aggregated unmet
passenger demand by destination or travel corridor. - Enter their
origin, destination, departure time, and available seats. - Offer a ride
when already travelling in a compatible direction. - Review proposed
pickup points and matched requests. - Accept, reject, or withdraw an
offer. - Track matched passengers and arrangement status.

Do not expose unnecessary passenger identity or precise location before
a match is accepted.

## 5. Core Functional Modules

### 5.1 Passenger Grouping Engine

Group passengers based on: - Same or nearby destinations. - Compatible
departure points. - Similar or compatible routes. - Departure and
arrival time constraints. - Number of people travelling together. -
Accessibility and declared travel requirements. - Maximum acceptable
waiting time. - Willingness to travel to a nearby pickup point.

Do not group passengers merely because their final destination names
match. Evaluate route compatibility, pickup distance, timing, and
requirements.

For each group, display its ID, passenger count, destination zone,
proposed pickup point, estimated journey time, compatibility score, and
explanation.

Provide an operator action to run or refresh grouping.

### 5.2 Dynamic Re-routing

Support service cancellation, delay, route closure, vehicle
unavailability, and vehicle capacity reduction.

When a disruption occurs: 1. Identify affected services and passengers.
2. Mark unavailable services or route segments. 3. Recalculate feasible
alternatives. 4. Reassess passenger groups and vehicle suitability. 5.
Update passenger recommendations. 6. Reassess pending and confirmed
allocations. 7. Flag confirmed journeys that are no longer feasible. 8.
Record all changes and reasons.

Do not silently overwrite a confirmed allocation. Any reassignment must
be visible and auditable.

Use a real routing provider where configured. If no live routing API is
available, use a clearly labelled simulated transport network and
deterministic fallback.

### 5.3 Capacity-Aware Official Transport Allocation

Maintain vehicle capacity and available seats accurately.

Rules: - Never allocate more passengers than available seats. - Keep
travelling parties together when feasible. - Respect accessibility and
vehicle suitability. - Recheck capacity immediately before
confirmation. - Reserve seats atomically to prevent simultaneous
requests claiming the same seats. - Release capacity when an allocation
is cancelled. - Display remaining seats after every confirmed
allocation.

Example: A replacement vehicle has 8 seats. If groups of 3 and 4 are
assigned, 1 seat remains. A further group of 2 cannot be assigned to it.

Capacity enforcement must happen in the backend/database, not only in
the frontend.

### 5.4 Transparent Prioritisation

Use documented, configurable rules to rank feasible allocation
candidates.

Potential factors: - Waiting time. - Arrival-time urgency. -
Availability of alternative journeys. - Number of passengers in a
travelling party. - Journey compatibility and operational feasibility.

Accessibility is a vehicle-suitability constraint, not a score that
could result in an unsuitable vehicle being assigned.

Every recommendation should show its priority score, score breakdown,
feasibility checks, and human-readable explanation.

Example: "Group G-04 was prioritised because its passengers have waited
longer, have fewer feasible alternatives, and can be accommodated by
this vehicle."

Operators must be able to inspect the rules and record a reason when
overriding a recommendation.

### 5.5 Passenger-Selected Alternative Journeys

This feature reduces operator workload.

For each affected passenger or group, generate a small set of feasible
alternatives based on submitted details.

Options may include: - Replacement bus or train. - Later departure. -
Different pickup point. - Route with transfers. - Journey to a nearby
transport hub. - Compatible shared journey.

Show departure time, estimated arrival, pickup point, transfers,
estimated duration, walking/waiting requirements, capacity status, and
whether the option is suggested or confirmed.

Passenger workflow: 1. Passenger opens their disruption notification or
dashboard. 2. System displays relevant alternatives. 3. Passenger
compares options. 4. Passenger selects or ranks preferred options
(e.g. first and second choice). 5. Preference appears on the operator
dashboard. 6. Operator sees consolidated preferences with capacity and
priority information. 7. Allocation engine or operator uses preferences
when making the final allocation. 8. Passenger receives a confirmed or
unavailable response.

Rules: - A preference is not a confirmed booking. - Never promise a seat
before the backend reserves it. - If the first choice is full, consider
the next feasible choice. - Allow preference updates until allocation is
confirmed. - Show passengers who have not submitted a preference.

### 5.6 Operator-Only Disruption Heat Map

Create an interactive heat map visible **only to authenticated operator
accounts**.

Visualise: - Number of affected passengers by location or geographic
grid. - Passenger density around pickup points. - Destination demand
concentrations. - Unresolved passenger demand. - Disruption-affected
zones. - Optionally, available replacement capacity by zone.

Requirements: - Use aggregated counts or geographic clusters, not public
display of individual identities. - Filter by disruption, destination,
allocation status, and time. - Include a legend and intensity scale. -
Let operators select an area to inspect aggregate demand and capacity. -
Refresh when passenger or allocation data changes. - Do not expose
precise passenger locations to other passengers or carpool providers. -
Enforce role-based access in the backend as well as frontend.

Use Leaflet and a suitable heat layer or clustered geographic
visualisation. Label sample data as simulated.

### 5.7 Community Carpooling Fallback

This is a major feature of the platform.

**Problem:** Official replacement transport may not have enough
capacity. Passengers without a confirmed official allocation should have
another possible way to reach their destination.

#### A. Identify unmet demand

After official allocation: 1. Identify passengers/groups without
confirmed official replacement. 2. Group compatible unallocated
passengers by destination, route corridor, origin, and departure time.
3. Calculate remaining demand for each group or corridor. 4. Publish an
aggregated carpool request to eligible users.

Example listing: - Destination: Central Railway Station - Passengers
awaiting transport: 5 - Preferred departure: 6:00--6:30 PM - Pickup
zone: North Bus Stand - Status: Seeking carpool provider

Do not publish passenger names, phone numbers, or precise live locations
in public listings.

#### B. Carpool provider workflow

An ordinary registered user opens the carpool section and sees
compatible unmet-demand listings, showing destination/corridor, general
pickup area, approximate passenger count, departure window, and relevant
non-identifying requirements.

A user already travelling in that direction can offer a ride by
submitting: - Origin and destination. - Departure date and time. -
Available seats. - Vehicle type and relevant suitability details. -
Proposed pickup area. - Optional route notes.

The system checks whether the provider's journey is compatible with
unmet demand.

#### C. Carpool matching

Match providers and passengers using: - Destination compatibility. -
Origin and pickup proximity. - Route overlap or acceptable detour. -
Departure-time compatibility. - Available seats. - Passenger group
size. - Declared travel requirements.

Never match more passengers than the provider's declared available
seats. A 3-seat offer cannot take a group of 4.

A provider's offer is not automatically confirmed. Provider and
passengers must review and accept the proposed arrangement.

#### D. Carpool status and safety

Status flow: - Open request - Offer received - Match proposed - Awaiting
passenger acceptance - Awaiting provider confirmation - Confirmed -
Cancelled - Completed

Safety and privacy: - Require authentication. - Provide a profile and
basic trust indicators. - Do not expose phone numbers or exact personal
details publicly. - Share contact and pickup details only after relevant
parties confirm. - Allow users to report or cancel an arrangement. -
Record offer, acceptance, cancellation, and completion events. - Clearly
state that community carpooling is user-provided and separate from
official transport. - Do not claim driver, vehicle, or identity
verification unless genuinely implemented.

For the prototype, implement authenticated demo users, explicit consent,
and visible status tracking. Do not claim legal or identity verification
unless it exists.

#### E. Operator visibility

Show: - Passengers still needing official transport. - Open carpool
requests. - Carpool offers received. - Proposed matches. - Confirmed
carpool arrangements. - Remaining unmatched demand.

Operators monitor the fallback without confusing community rides with
official replacement vehicles.

## 6. End-to-End Workflow

1.  A service is cancelled, delayed, or affected by a closure.
2.  The system identifies affected passengers.
3.  It checks origin, destination, group size, timing, and requirements.
4.  Compatible journeys are grouped.
5.  Alternative journeys are generated.
6.  Passengers select or rank preferred alternatives.
7.  Operator dashboard displays preferences, demand, capacity, and heat
    map.
8.  Official replacement seats are allocated using capacity and priority
    rules.
9.  Unresolved demand is identified.
10. Compatible unallocated passengers are grouped into aggregated
    carpool listings.
11. Ordinary users travelling along compatible routes offer spare seats.
12. The matching engine checks route, timing, suitability, and capacity.
13. Passengers and providers accept the proposed arrangement.
14. Both dashboards update statuses and unresolved demand.
15. All decisions and changes are recorded.

## 7. Suggested System Architecture

  -----------------------------------------------------------------------
  Module                              Responsibility
  ----------------------------------- -----------------------------------
  Authentication & Roles              Passenger, operator, and carpool
                                      provider access

  Passenger Management                Profiles, journey requests,
                                      requirements

  Disruption Manager                  Cancellations, delays, closures,
                                      affected services

  Passenger Grouping Engine           Groups compatible journeys

  Route Engine                        Generates and compares alternatives

  Passenger Preference Manager        Stores ranked recovery preferences

  Priority Engine                     Applies explainable prioritisation

  Official Allocation Engine          Allocates replacement seats safely

  Heat Map Service                    Aggregates geographic demand for
                                      operators

  Carpool Demand Manager              Publishes aggregated unmet demand

  Carpool Matching Engine             Matches user offers with unmet
                                      demand

  Notification Service                Sends journey and allocation
                                      updates

  Operator Dashboard                  Disruption, capacity, preferences,
                                      heat map, demand

  Passenger Dashboard                 Alternatives, preferences,
                                      allocations, carpooling

  Audit Log                           Decisions, confirmations, changes,
                                      overrides
  -----------------------------------------------------------------------

### High-level data flow

``` text
                 DISRUPTION
                      |
                      v
            Identify Affected Passengers
                      |
                      v
             Passenger Grouping Engine
                      |
                      v
             Alternative Route Engine
                      |
             +--------+--------+
             |                 |
             v                 v
      Passenger Dashboard   Operator Dashboard
      Select Preferences    Heat Map + Demand
             |                 |
             +--------+--------+
                      |
                      v
              Priority Engine
                      |
                      v
           Official Allocation Engine
                      |
             +--------+--------+
             |                 |
             v                 v
       Confirmed Official   Unresolved Demand
         Allocations              |
                                  v
                        Carpool Demand Clustering
                                  |
                                  v
                         Community Carpool Offers
                                  |
                                  v
                           Carpool Matching
                                  |
                                  v
                       Passenger + Provider Consent
                                  |
                                  v
                         Confirmed Carpool
```

## 8. Core Data Entities

### Passenger

`passenger_id`, `name`, `current_location`, `origin`, `destination`,
`group_size`, `preferred_departure_window`, `latest_arrival_time`,
`maximum_wait_time`, `travel_requirements`, `journey_status`

### Disruption

`disruption_id`, `service_id`, `disruption_type`,
`affected_route_or_segment`, `start_time`, `estimated_end_time`,
`status`

### Vehicle

`vehicle_id`, `vehicle_type`, `capacity`, `available_seats`,
`current_location`, `route_or_destination`, `accessibility_features`,
`availability_status`

### Passenger Group

`group_id`, `passenger_ids`, `destination_zone`, `pickup_point`,
`combined_group_size`, `compatibility_score`, `group_status`

### Journey Option

`journey_option_id`, `passenger_or_group_id`, `route_details`,
`departure_time`, `estimated_arrival_time`, `transfers`,
`required_walking_distance`, `capacity_status`, `option_status`

### Passenger Preference

`preference_id`, `passenger_id`, `journey_option_id`, `preference_rank`,
`submitted_at`, `preference_status`

### Official Allocation

`allocation_id`, `group_id`, `vehicle_id`, `allocated_seats`,
`priority_score`, `decision_explanation`, `allocation_status`,
`created_at`, `confirmed_at`

### Carpool Request

`carpool_request_id`, `passenger_group_id`, `origin_zone`,
`destination_zone`, `passenger_count`, `departure_window`,
`travel_requirements`, `request_status`

### Carpool Offer

`carpool_offer_id`, `provider_user_id`, `origin`, `destination`,
`departure_time`, `available_seats`, `vehicle_details`, `pickup_zone`,
`offer_status`

### Carpool Match

`carpool_match_id`, `carpool_request_id`, `carpool_offer_id`,
`matched_seats`, `match_status`, `passenger_acceptance_status`,
`provider_confirmation_status`, `created_at`

### Audit Event

`event_id`, `event_type`, `related_entity_id`, `decision_or_change`,
`reason`, `actor_id`, `timestamp`

## 9. Allocation and Matching Logic

### 9.1 Official transport allocation

Separate feasibility from prioritisation.

Feasibility checks: - Enough available seats. - Vehicle satisfies travel
requirements. - Route is not blocked. - Pickup and destination are
compatible. - Hard arrival-time constraints are satisfied.

A prototype priority score may use:

``` text
priority_score =
    (waiting_time_weight * normalized_waiting_time)
  + (urgency_weight * normalized_time_urgency)
  + (scarcity_weight * alternative_scarcity)
  + (group_weight * group_integrity)
  + (preference_weight * passenger_preference_match)
```

Weights must be documented and configurable. Accessibility is a
suitability constraint.

Before confirmation, recheck capacity, reserve seats atomically, update
remaining capacity, and record the decision.

### 9.2 Passenger preferences

Preferences influence allocation but cannot override safety,
feasibility, or capacity constraints.

If the first choice is unavailable, consider the next feasible choice
and explain why. Operators should see: - First choice available. - First
choice full; second choice feasible. - No selected option feasible. - No
preference submitted.

### 9.3 Carpool matching

Create a proposed match only if: - Provider route is compatible with
destination. - Pickup detour is within a configured threshold. -
Departure times overlap sufficiently. - Provider has enough spare
seats. - Vehicle suitability meets declared requirements. - Provider and
passenger group can review the arrangement.

Carpool capacity is enforced independently from official transport
capacity. A community carpool must never be counted as an official
allocation.

## 10. Suggested Technology Stack

  -----------------------------------------------------------------------
  Layer                   Suggested technology    Purpose
  ----------------------- ----------------------- -----------------------
  Frontend                React + TypeScript +    Web application
                          Vite                    

  Styling                 Tailwind CSS            Responsive UI

  Maps                    Leaflet + OpenStreetMap Interactive map and
                                                  heat map

  Charts                  Recharts                Dashboard analytics

  Backend                 Python + FastAPI        APIs and business logic

  Database                PostgreSQL; SQLite for  Persistent data
                          local MVP               

  ORM                     SQLAlchemy              Database access

  Validation              Pydantic                API validation

  Real-time updates       WebSockets or Supabase  Live dashboard updates
                          Realtime                

  Routing                 OSRM, GraphHopper, or   Journey estimates
                          configurable provider   

  Optimisation            Python; OR-Tools if     Capacity-constrained
                          useful                  assignment

  Notifications           Firebase Cloud          Passenger alerts
                          Messaging or equivalent 
  -----------------------------------------------------------------------

The product must remain demonstrable without paid API keys. Clearly
label simulated and estimated data.

## 11. Minimum Viable Product

### Must-have

-   Separate passenger and operator dashboards.
-   Role-based access.
-   Passenger journey submission.
-   Passenger grouping.
-   Disruption simulation.
-   Alternative journey generation.
-   Passenger alternative selection and preference submission.
-   Operator view of passenger preferences.
-   Capacity-safe official allocation.
-   Explainable prioritisation.
-   Unresolved demand management.
-   Operator-only disruption heat map.
-   Community carpool demand listings.
-   User carpool offer submission.
-   Carpool matching with seat-capacity checks.
-   Passenger and provider consent before confirmation.
-   Audit log.
-   Demo dataset and reset functionality.

### Optional enhancements

-   Live notifications.
-   Real transport feeds.
-   Advanced multi-vehicle optimisation.
-   Live vehicle tracking.
-   Identity or vehicle verification integrations.
-   Historical disruption analytics.

## 12. Demonstration Scenario

### Evening commute cancellation

Create a reproducible scenario: - 24 affected passengers. - Multiple
destinations and pickup areas. - Different group sizes and arrival-time
constraints. - 3 official replacement vehicles. - Capacities: 8, 7, and
5 seats. - Total official replacement capacity: 20 seats.

Do not force exactly 20 allocations if journey constraints make some
assignments infeasible.

### Demonstration sequence

1.  Operator opens the dashboard and sees the normal network state.
2.  Operator triggers a bus cancellation.
3.  Affected passengers appear in the passenger dashboard.
4.  Grouping engine clusters compatible journeys.
5.  Route engine generates alternatives.
6.  Passengers select preferred alternatives.
7.  Operator dashboard displays those preferences.
8.  Operator runs smart allocation.
9.  System allocates suitable passengers without overbooking.
10. Heat map highlights areas with high affected-passenger density.
11. Remaining passengers are grouped into carpool demand listings.
12. A normal user offers spare seats through the passenger-facing
    carpool section.
13. Matching engine checks route, time, requirements, and capacity.
14. Passengers and provider accept the proposed match.
15. Both dashboards update confirmed carpool and remaining demand.
16. Audit log shows decisions throughout the scenario.

## 13. Success Metrics

-   Percentage of affected passengers assigned official replacement
    transport.
-   Percentage of unmet demand matched through community carpooling.
-   Average time from disruption to confirmed recovery option.
-   Official vehicle seat utilisation.
-   Carpool seat utilisation.
-   Over-allocation count --- must remain zero.
-   Number of passengers with no feasible option.
-   Percentage of passengers whose selected preference is satisfied.
-   Average additional journey time.
-   Percentage of allocation decisions with an explanation.
-   Operator manual steps reduced through passenger preference
    collection.

Measure results using repeatable test scenarios. Do not claim
improvements without a baseline.

## 14. Reliability, Privacy, Safety, and Fairness

-   Enforce role-based access in the backend.
-   Keep the heat map operator-only.
-   Use aggregated geographic counts for heat maps.
-   Do not publicly expose passenger identities or precise live
    locations.
-   Share carpool contact details only after relevant parties consent.
-   Never show a suggested journey as confirmed before reservation.
-   Enforce capacity constraints in backend transactions.
-   Record operator overrides and reasons.
-   Label simulated and estimated information.
-   Keep official transport and community carpool statuses separate.
-   Provide cancellation and reporting flows for carpool arrangements.
-   Do not claim identity, driver, or vehicle verification unless
    implemented.
-   Collect only information needed for journey coordination.
-   Provide a fallback if routing or live data services fail.

## 15. Key Innovation

The Stranded Network goes beyond conventional route planning:

1.  **Coordinated recovery:** groups passengers with compatible
    journeys.
2.  **Passenger-driven preferences:** passengers select alternatives,
    reducing operator workload.
3.  **Capacity-safe allocation:** allocates limited replacement seats
    responsibly.
4.  **Explainable decisions:** operators inspect why a group was
    prioritised.
5.  **Disruption heat map:** shows geographic demand and unresolved
    cases.
6.  **Community carpooling fallback:** turns unmet demand into
    aggregated ride requests that ordinary users travelling in the same
    direction can help fulfil.

The carpool feature can unlock spare seats in journeys already being
made by ordinary users when official capacity runs out.

## 16. Scope and Assumptions

For the initial prototype: - Use one sample city or small fictional
transport network. - Simulate passengers, disruptions, official
vehicles, and carpool providers where real data is unavailable. -
Support a limited number of disruption types. - Use configurable
thresholds for pickup detours and time compatibility. - Treat routing
and arrival estimates as estimates unless backed by live data. - Keep
operators in control of official allocations. - Require explicit
provider and passenger acceptance for community carpool matches.

**Final goal:** Build a complete passenger-and-operator coordination
platform that recovers journeys through official replacement transport
first, then helps resolve remaining demand through community carpooling
--- while maintaining transparency, privacy, and strict capacity
control.
