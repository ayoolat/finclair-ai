from enum import Enum


class UserGoalType(str, Enum):
    SMART_MONEY_SAVING = "smart_money_saving"
    TRACK_MY_SPENDING = "track_my_spending"
    STICK_TO_A_BUDGET = "stick_to_a_budget"
    FEEL_MORE_IN_CONTROL = "feel_more_in_control"


class OtpType(str, Enum):
    EMAIL_VERIFICATION = "email_verification"
    PASSCODE_RESET = "passcode_reset"
