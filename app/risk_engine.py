from datetime import datetime, timezone

def evaluate(due_date: datetime, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    remaining = (due_date - now).total_seconds() / 86400
    if remaining < 0:
        return "overdue", 1.0
    if remaining < 7:
        return "due_soon", 0.7
    return "pending", 0.2
