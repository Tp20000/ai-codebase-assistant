from datetime import datetime

def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")

def calculate_total(items: list[str]) -> float:
    return sum(len(item) * 1.5 for item in items)

def validate_email(email: str) -> bool:
    return "@" in email and "." in email