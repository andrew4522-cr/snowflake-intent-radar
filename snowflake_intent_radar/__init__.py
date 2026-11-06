"""
snowflake-intent-radar: Sub-24h Social Buyer-Intent Scanner via 64-Bit Snowflake Math.
"""

from .radar import (
    extract_snowflake_datetime,
    verify_snowflake_recency,
    format_age_badge,
    is_strictly_native_english,
    is_valid_buyer_opportunity,
    is_valid_1st_connection_post,
    is_linkedin_1st_connection,
    parse_linkedin_card,
    parse_x_card,
    classify_track_and_subangle,
    compute_suitability_score,
    generate_tailored_response,
    evaluate_post,
    TWITTER_EPOCH_MS,
)

__version__ = "1.0.0"
__all__ = [
    "extract_snowflake_datetime",
    "verify_snowflake_recency",
    "format_age_badge",
    "is_strictly_native_english",
    "is_valid_buyer_opportunity",
    "is_valid_1st_connection_post",
    "is_linkedin_1st_connection",
    "parse_linkedin_card",
    "parse_x_card",
    "classify_track_and_subangle",
    "compute_suitability_score",
    "generate_tailored_response",
    "evaluate_post",
    "TWITTER_EPOCH_MS",
]
