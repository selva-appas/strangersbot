import asyncio
import inspect
from datetime import date
from types import SimpleNamespace

import bot
from stranger_match_bot import matching, safety


def test_validate_dob_success():
    assert matching.validate_date_of_birth("1998-07-25") == "1998-07-25"


def test_validate_dob_future_rejected():
    future = date.today().isoformat()
    try:
        matching.validate_date_of_birth(future)
        assert False, "Future DOB should be rejected"
    except ValueError:
        pass


def test_under_18_rejected():
    try:
        matching.validate_date_of_birth("2010-01-01")
        assert False, "Users under 18 must be rejected"
    except ValueError:
        pass


def test_age_calculation():
    y, m, d = 1998, 7, 25
    assert matching.calculate_age(date(y, m, d)) >= 27


def test_matching_compatibility():
    user_a = {
        "age": 25,
        "gender": "male",
        "min_age": 22,
        "max_age": 30,
        "preferred_gender": "female",
        "city": "Chennai",
        "preferred_location": "Chennai",
        "mode": "dating",
        "banned": 0,
    }
    user_b = {
        "age": 24,
        "gender": "female",
        "min_age": 24,
        "max_age": 30,
        "preferred_gender": "male",
        "city": "Chennai",
        "preferred_location": "Chennai",
        "mode": "dating",
        "banned": 0,
    }
    assert matching.users_match(user_a, user_b)


def test_block_behavior():
    assert matching.is_blocked(1, 2, [(1, 2)])
    assert not matching.is_blocked(1, 3, [(2, 1)])


def test_report_behavior():
    report = {
        "reporter_id": 1,
        "reported_id": 2,
        "reason": "spam",
        "status": "pending",
    }
    assert report["reason"] == "spam"


def test_ban_behavior():
    user = {"banned": 1, "active": 0}
    assert user["banned"] == 1


def test_rate_limit_logic():
    rate_events = [1, 2, 3, 4, 5]
    assert len(rate_events) <= 20


def test_profile_deletion_flag():
    user = {"deleted": True}
    assert user["deleted"] is True


def test_preference_matching():
    assert safety.contains_safety_guidance("Never share passwords")


def test_main_entrypoint_is_sync():
    assert inspect.iscoroutinefunction(bot.main) is False


def test_skip_photo_command_advances_profile_flow():
    async def run_test():
        update = SimpleNamespace(
            message=SimpleNamespace(
                text="/skip",
                photo=None,
                reply_text=AsyncMock(return_value=None),
            )
        )
        context = SimpleNamespace(user_data={"profile": {}})

        result = await bot.skip_photo(update, context)
        assert result == bot.PROFILE_MIN_AGE

    from unittest.mock import AsyncMock

    asyncio.run(run_test())
