"""Transparent prioritisation (spec 5.4 and 9.1).

    priority_score = waiting_weight    * normalised_waiting_time
                   + urgency_weight    * normalised_time_urgency
                   + scarcity_weight   * alternative_scarcity
                   + group_weight      * group_integrity
                   + preference_weight * passenger_preference_match

Each factor is in 0..1. Weights and thresholds are operator-configurable. Accessibility is
deliberately absent: it is a feasibility constraint, so no score can place a party on an
unsuitable vehicle.
"""
from ..models import Journey, JourneyOption, Preference, Vehicle

FACTOR_LABELS = {
    "waiting": "Waiting time",
    "urgency": "Arrival urgency",
    "scarcity": "Lack of alternatives",
    "group": "Keeping the party together",
    "preference": "Passenger preference",
}


def preference_match(prefs: list[Preference], vehicle_id: str, cfg: dict) -> tuple[float, str]:
    live = [p for p in prefs if p.status != "invalidated"]
    if not live:
        return cfg["no_preference_value"], "no_preference"
    for p in sorted(live, key=lambda p: p.rank):
        if p.option.vehicle_id == vehicle_id:
            if p.rank == 1:
                return 1.0, "first_choice"
            return cfg["second_choice_value"], "second_choice"
    return 0.0, "other_feasible"


def score(j: Journey, v: Vehicle, arrival: int, options: list[JourneyOption],
          prefs: list[Preference], weights: dict, cfg: dict, now: int) -> tuple[float, dict, str]:
    waited = max(0, now - j.reported_min)
    slack = max(0, j.latest_arrival - arrival)
    walkups = sum(1 for o in options if o.status == "active" and not o.reservable and o.meets_deadline)
    pref_value, outcome = preference_match(prefs, v.id, cfg)

    factors = {
        "waiting": min(1.0, waited / cfg["waiting_cap_min"]),
        "urgency": max(0.0, 1 - slack / cfg["urgency_horizon_min"]),
        "scarcity": max(0.0, 1 - walkups / 3),
        "group": min(1.0, j.party_size / cfg["group_full_party"]),
        "preference": pref_value,
    }
    total = sum(weights[k] * factors[k] for k in factors)
    breakdown = {
        "factors": {k: {"label": FACTOR_LABELS[k], "value": round(factors[k], 3),
                        "weight": weights[k], "points": round(weights[k] * factors[k], 3)}
                    for k in factors},
        "inputs": {"waited_min": waited, "slack_min": slack, "walkup_alternatives": walkups,
                   "party_size": j.party_size},
    }
    return round(total, 3), breakdown, outcome


def triage_note(j: Journey, breakdown: dict, group_label: str | None, reduction_pct: int | None) -> str:
    """Why this party won a scarce seat. Names its strongest factor and any accessibility need."""
    if not reduction_pct:
        return ""
    label, value = max(((f["label"], f["value"]) for f in breakdown["factors"].values()), key=lambda f: f[1])
    needs = {"wheelchair": "wheelchair requirement", "step_free": "step-free requirement"}
    parts = [needs[r] for r in j.requirements if r in needs]
    parts.append(f"highest {label.lower()} score ({value:.2f})")
    subject = f"Group {group_label}" if group_label else j.ref
    return f"Prioritised under {reduction_pct}% fleet reduction: {subject} has {' + '.join(parts)}. "


def describe(j: Journey, v: Vehicle, total: float, breakdown: dict, outcome: str, group_label: str | None) -> str:
    """Human-readable reason, naming the factors that actually drove the score."""
    inputs = breakdown["inputs"]
    ranked = sorted(breakdown["factors"].items(), key=lambda kv: -kv[1]["points"])
    phrases = {
        "waiting": f"has waited {inputs['waited_min']} min",
        "urgency": f"has only {inputs['slack_min']} min of slack before the arrival deadline",
        "scarcity": ("has no walk-up alternative that arrives in time" if inputs["walkup_alternatives"] == 0
                     else f"has {inputs['walkup_alternatives']} walk-up alternative(s) in time"),
        "group": f"is a party of {inputs['party_size']} kept together",
        "preference": {"first_choice": "chose this vehicle first", "second_choice": "chose this vehicle second",
                       "no_preference": "gave no preference", "other_feasible": "ranked other options"}[outcome],
    }
    top = [phrases[k] for k, f in ranked[:3] if f["points"] > 0] or ["met every rule"]
    subject = f"{j.ref} ({group_label})" if group_label else j.ref
    pref_note = {
        "first_choice": "First choice honoured.",
        "second_choice": "First choice unavailable or full; second choice honoured.",
        "no_preference": "No preference submitted.",
        "other_feasible": "Neither ranked option could be honoured; this was the next feasible vehicle.",
    }[outcome]
    return (f"{subject} was placed on {v.id} with priority {total:.2f} because it "
            f"{', '.join(top[:-1]) + ' and ' + top[-1] if len(top) > 1 else top[0]}, "
            f"and the vehicle passed every feasibility check. {pref_note}")
