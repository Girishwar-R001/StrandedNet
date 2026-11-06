# BUILD THE STRANDED NETWORK — COMPLETE FULL-STACK APPLICATION

Act as a senior full-stack developer, software architect, UI/UX designer, and optimisation engineer.

I want you to build a complete, functional, hackathon-ready application called:

**THE STRANDED NETWORK**
*Dynamic Travel Recovery, Passenger Coordination & Community Carpooling Platform*

I have attached `The_Stranded_Network_Main.md`. Read the entire document carefully. It contains the complete project requirements, functionality, workflows, and system architecture.

Your responsibility is to actually develop the application, not just generate a plan or a static UI.

## 1. Understand the product first

The application must have TWO COMPLETELY SEPARATE DASHBOARDS:

**A. Passenger Dashboard**

For ordinary passengers and community carpool providers.

**B. Operator Dashboard**

For transport authorities/operators who manage disruptions, replacement vehicles, passenger allocation, and unresolved demand.

Both dashboards must communicate with the same backend and database, with appropriate role-based permissions.

## 2. Most important features to implement

Implement all six original capabilities:

1. Passenger grouping based on destination, departure point, travel requirements, and time constraints.
2. Dynamic re-routing after cancellations, delays, or route closures.
3. Capacity-aware allocation of vehicles and seats, without over-allocation.
4. Transparent prioritisation rules that operators can inspect.
5. Alternative journey suggestions for passengers who cannot be accommodated.
6. Disruption dashboard showing affected passengers, available capacity, allocation status, and unresolved demand.

Additionally, implement these three major features:

### FEATURE A — Community Carpooling

When official replacement transport cannot accommodate everyone:

- Automatically identify passengers without confirmed replacement transport.
- Cluster compatible unallocated passengers by destination, origin, route, and departure time.
- Publish aggregated carpool requests in the passenger-facing app.
- Allow ordinary registered users travelling in a compatible direction to offer spare seats.
- Match providers with suitable passenger groups.
- Check available seats, route compatibility, departure time, and passenger requirements.
- Allow passengers and providers to review and accept proposed matches.
- Update both dashboards when a carpool is confirmed.

Carpool providers are ordinary users, not transport operators.

Implement proper consent, authentication, privacy, capacity checks, and status tracking.

Do not expose passengers' personal information publicly.

### FEATURE B — Operator-Only Disruption Heat Map

Implement a real interactive heat map.

It must show:
- Number of affected passengers in each area.
- Passenger density.
- Locations with high unresolved demand.
- Destination demand concentrations.
- Disruption-affected areas.
- Available replacement capacity by area where data permits.

This feature must ONLY be accessible to authenticated operators.

Use Leaflet and OpenStreetMap. Use aggregated geographic data and protect passenger privacy.

### FEATURE C — Passenger-Selected Alternative Journeys

This feature is intended to reduce operator workload.

The system should generate alternative journeys based on each passenger's:
- Current location.
- Destination.
- Group size.
- Preferred departure time.
- Latest acceptable arrival time.
- Travel requirements.

Passengers should be able to compare options and select or rank their preferred alternatives.

These preferences must immediately appear on the operator dashboard.

Operators should see:
- Passenger's first preference.
- Second preference.
- Availability of each option.
- Number of passengers preferring each alternative.
- Passengers who have not selected an option.

The allocation engine should consider these preferences while respecting vehicle capacity and prioritisation rules.

IMPORTANT: Selecting an alternative is NOT equivalent to confirming a booking. Only a successful backend allocation can confirm a seat.

## 3. Application architecture

Use a clean, modular full-stack architecture.

Suggested stack:

Frontend:
- React
- TypeScript
- Vite
- Tailwind CSS
- Lucide React
- Recharts
- Leaflet

Backend:
- Python
- FastAPI
- Pydantic
- SQLAlchemy

Database:
- PostgreSQL, or SQLite for the initial MVP.

Algorithms:
- Python-based passenger grouping.
- Capacity-constrained allocation.
- Explainable prioritisation.
- Carpool matching.
- OR-Tools if it provides a meaningful optimisation improvement.

Use real APIs where practical, but ensure the complete demo works without paid API keys.

If external routing or transport feeds are unavailable, build a deterministic simulated transport network. Clearly label simulated data.

## 4. Operator dashboard

Build the following sections:

1. Overview and live statistics.
2. Interactive disruption map.
3. Operator-only passenger heat map.
4. Passenger management.
5. Passenger grouping.
6. Vehicle management.
7. Smart allocation engine.
8. Passenger preference management.
9. Disruption simulation.
10. Unresolved passenger demand.
11. Community carpool monitoring.
12. Allocation explanations.
13. Audit logs.

Every important action must connect to actual backend functionality.

## 5. Passenger dashboard

Build the following sections:

1. Passenger overview.
2. Journey registration.
3. Current disruption information.
4. Recommended alternative journeys.
5. Alternative selection and preference ranking.
6. Allocation status and journey tracking.
7. Assigned replacement transport.
8. Unresolved journey status.
9. Community carpool requests.
10. Offer a carpool.
11. Carpool match and confirmation status.
12. Notifications.

Make the interface simple enough that an ordinary passenger can understand what to do without assistance.

## 6. Critical algorithm requirements

Do not compromise on these.

**Passenger grouping:** Consider actual route and time compatibility, not just destination names.

**Official allocation:** Never exceed available vehicle capacity. Use backend validation and atomic database reservations.

**Prioritisation:** Use documented and configurable rules. Explain every allocation.

**Passenger preferences:** Consider first and second choices without overriding feasibility or capacity.

**Carpool matching:** Independently enforce available seats, route compatibility, timing, and consent.

**Dynamic rerouting:** Reassess affected allocations when a disruption or vehicle change occurs. Never silently overwrite confirmed bookings.

**Heat map:** Use aggregated data and enforce operator-only access at the backend level.

## 7. Design requirements

I want a premium, professional, production-style interface.

Design inspiration:
- Linear
- Stripe Dashboard
- Modern logistics and transport management software.

Visual direction:
- Clean and minimal.
- Strong information hierarchy.
- Excellent typography.
- Consistent spacing.
- Refined tables and charts.
- Subtle borders.
- Professional map presentation.
- Responsive layouts.

Avoid:
- Excessive gradients.
- Glowing borders.
- Generic AI-generated dashboard design.
- Unnecessary animations.
- Oversized rounded cards.
- Random decorative elements.
- Cluttered layouts.

Use a sophisticated neutral palette with restrained accent colours.

The passenger dashboard should feel friendly and intuitive. The operator dashboard should feel like a serious transport operations system.

Do not make both dashboards look identical.

## 8. Demonstration scenario

Create a complete reproducible scenario:

- 24 affected passengers.
- Multiple destinations.
- Different pickup locations.
- Different passenger group sizes.
- Different arrival-time constraints.
- 3 replacement vehicles.
- Capacities of 8, 7, and 5 seats.

Total official replacement capacity: 20 seats.

Demonstrate:
1. Operator triggers a cancellation.
2. Affected passengers are identified.
3. Passengers are grouped.
4. Alternative journeys are generated.
5. Passengers select preferred alternatives.
6. Operator sees their preferences.
7. Smart allocation assigns available seats.
8. Heat map displays affected passenger concentrations.
9. Remaining passengers become carpool requests.
10. An ordinary user offers a carpool.
11. The system matches the offer with suitable passengers.
12. Passengers and provider confirm the arrangement.
13. Both dashboards update.

Do not force allocations that violate journey compatibility or capacity.

## 9. Development instructions

Work directly in the project directory.

Before coding:
- Inspect existing project files.
- Read the attached MD specification.
- Establish the architecture.
- Identify the core data entities.
- Plan the API endpoints.

Then implement in this order:

1. Backend and database.
2. Passenger grouping and allocation algorithms.
3. Disruption and re-routing logic.
4. Passenger preference functionality.
5. Carpool matching.
6. Frontend dashboards.
7. Interactive maps and heat map.
8. Integration and testing.
9. Documentation.

Write meaningful tests for capacity enforcement, grouping, prioritisation, passenger preferences, carpool matching, consent, and disruption recovery.

Do not leave important buttons as placeholders.

Do not stop after creating the frontend.

Do not just provide code snippets for me to assemble manually.

Actually create and modify the project files, run the application, test it, and fix errors.

If a feature requires an unavailable external service, implement a functional simulated alternative and document the limitation.

## 10. Final deliverables

I expect:

- Fully functional passenger dashboard.
- Fully functional operator dashboard.
- Working backend.
- Database integration.
- Passenger grouping algorithm.
- Smart allocation engine.
- Dynamic disruption simulation.
- Passenger preference system.
- Operator-only heat map.
- Community carpooling and matching.
- Audit logs.
- Demo data.
- Automated tests.
- README.md.
- SETUP.md.
- Environment variable example file.

At completion, give me:
- Exact commands to run the application.
- How to access each dashboard.
- Demo login credentials.
- How to run the demonstration scenario.
- What is simulated and what uses real services.

**FINAL INSTRUCTION:**

Build a complete working product, not a UI prototype.

The most important thing is that the entire recovery workflow works end-to-end.

When a transport service is cancelled, the system must coordinate passengers, collect their preferences, allocate official replacement transport fairly, identify remaining unmet demand, and use community carpooling as a fallback.

Make this application something I can confidently demonstrate to hackathon judges.