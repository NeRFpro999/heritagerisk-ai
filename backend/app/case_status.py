"""Risk Case lifecycle transition rules."""

CASE_STATUSES = ["Draft", "Needs Review", "Verified", "Routed", "Closed"]

ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "Draft": ("Needs Review",),
    "Needs Review": ("Verified", "Draft"),
    "Verified": ("Routed", "Needs Review"),
    "Routed": ("Closed",),
    "Closed": (),
}


def allowed_next_statuses(current_status: str) -> tuple[str, ...]:
    return ALLOWED_TRANSITIONS.get(current_status, ())


def invalid_transition_message(from_status: str, to_status: str) -> str:
    allowed = allowed_next_statuses(from_status)
    allowed_text = ", ".join(allowed) if allowed else "none"
    return (
        f"Invalid transition from {from_status} to {to_status}. "
        f"Allowed next states: {allowed_text}."
    )
