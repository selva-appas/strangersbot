from __future__ import annotations

from datetime import date, datetime


def validate_date_of_birth(raw_value: str) -> str:
    if not isinstance(raw_value, str):
        raise ValueError("Date of birth must be provided in YYYY-MM-DD format.")
    value = raw_value.strip()
    try:
        dob = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Invalid date. Use YYYY-MM-DD format.") from exc
    today = date.today()
    if dob > today:
        raise ValueError("Date of birth cannot be in the future.")
    age = calculate_age(dob)
    if age < 18:
        raise ValueError("You must be 18 or older to use StrangerMatch.")
    return dob.isoformat()


def calculate_age(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def normalize_gender(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower()


def is_age_compatible(age_a: int, age_b: int, min_age_a: int | None, max_age_a: int | None, min_age_b: int | None, max_age_b: int | None) -> bool:
    lower = max(min_age_a or 18, min_age_b or 18)
    upper = min(max_age_a or 120, max_age_b or 120)
    if age_a < lower or age_a > upper:
        return False
    if age_b < lower or age_b > upper:
        return False
    return True


def genders_compatible(gender_a: str | None, preferred_gender_a: str | None, gender_b: str | None, preferred_gender_b: str | None) -> bool:
    if not gender_a or not gender_b:
        return False
    if not preferred_gender_a or not preferred_gender_b:
        return False
    a_pref = normalize_gender(preferred_gender_a)
    b_pref = normalize_gender(preferred_gender_b)
    a_gender = normalize_gender(gender_a)
    b_gender = normalize_gender(gender_b)
    if a_gender == a_pref and b_gender == b_pref:
        return True
    if a_pref in ("any", "all", "everyone"):
        return True
    if b_pref in ("any", "all", "everyone"):
        return True
    return a_gender == b_pref and b_gender == a_pref


def users_match(user_a: dict, user_b: dict) -> bool:
    if not user_a or not user_b:
        return False
    if user_a.get("banned") == 1 or user_b.get("banned") == 1:
        return False
    if user_a.get("active") == 1 and user_b.get("active") == 1:
        return False

    age_a = user_a.get("age")
    age_b = user_b.get("age")
    if age_a is None or age_b is None:
        return False
    min_age_a = user_a.get("min_age")
    max_age_a = user_a.get("max_age")
    min_age_b = user_b.get("min_age")
    max_age_b = user_b.get("max_age")
    if not is_age_compatible(age_a, age_b, min_age_a, max_age_a, min_age_b, max_age_b):
        return False

    if not genders_compatible(
        user_a.get("gender"),
        user_a.get("preferred_gender"),
        user_b.get("gender"),
        user_b.get("preferred_gender"),
    ):
        return False

    a_city = str(user_a.get("city") or "").strip().lower()
    b_city = str(user_b.get("city") or "").strip().lower()
    a_pref_location = str(user_a.get("preferred_location") or "").strip().lower()
    b_pref_location = str(user_b.get("preferred_location") or "").strip().lower()
    if a_city and b_city and a_pref_location and b_pref_location:
        if a_pref_location not in a_city and a_city not in a_pref_location:
            return False
        if b_pref_location not in b_city and b_city not in b_pref_location:
            return False

    if str(user_a.get("mode") or "").lower() != str(user_b.get("mode") or "").lower():
        return False

    return True


def is_blocked(user_a_id: int, user_b_id: int, blocks: list[tuple[int, int]] | None = None) -> bool:
    if not blocks:
        return False
    return (user_a_id, user_b_id) in blocks or (user_b_id, user_a_id) in blocks
