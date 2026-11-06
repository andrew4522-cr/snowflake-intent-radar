import unittest
from datetime import datetime, timedelta, timezone

from snowflake_intent_radar import (
    TWITTER_EPOCH_MS,
    compute_suitability_score,
    evaluate_post,
    extract_snowflake_datetime,
    is_strictly_native_english,
    is_valid_buyer_opportunity,
    verify_snowflake_recency,
)


class TestSnowflakeIntentRadar(unittest.TestCase):
    def test_linkedin_and_x_snowflake_math(self):
        target_dt = datetime(2026, 11, 6, 10, 0, 0, tzinfo=timezone.utc)
        epoch_ms = int(target_dt.timestamp() * 1000)

        # Construct synthetic 64-bit LinkedIn activity ID and X status ID
        li_snowflake = epoch_ms << 22
        x_snowflake = (epoch_ms - TWITTER_EPOCH_MS) << 22

        li_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{li_snowflake}/"
        x_url = f"https://x.com/founder/status/{x_snowflake}"

        self.assertEqual(extract_snowflake_datetime(li_url), target_dt)
        self.assertEqual(extract_snowflake_datetime(x_url), target_dt)

        # Verify <24h check when evaluated 3 hours later vs 30 hours later
        res_fresh = verify_snowflake_recency(li_url, max_hours=24.0, now_utc=target_dt + timedelta(hours=3))
        self.assertTrue(res_fresh["within_window"])
        self.assertEqual(res_fresh["age_hours"], 3.0)

        res_stale = verify_snowflake_recency(li_url, max_hours=24.0, now_utc=target_dt + timedelta(hours=30))
        self.assertFalse(res_stale["within_window"])

    def test_buyer_intent_vs_supply_side_noise(self):
        # Genuine founder distress / recommendation request
        distress_post = (
            "We are struggling with our HubSpot and n8n workflow automation as we scale across Europe. "
            "Can anyone recommend a strong AI automation consultant or fractional RevOps architect? DM me!"
        )
        self.assertTrue(is_valid_buyer_opportunity("Founder at SaaS", distress_post, require_target_geo=True))

        # Job-seeker / #opentowork pitch (must be rejected)
        seeker_post = "I am currently looking for my next role as a Fractional CMO! #opentowork DM me if you are hiring."
        self.assertFalse(is_valid_buyer_opportunity("Marketer", seeker_post, require_target_geo=True))

        # Lead-magnet engagement bait (must be rejected)
        bait_post = "I built an AI agent that replaces SDRs. Comment 'AGENT' and I'll send you the workflow!"
        self.assertFalse(is_valid_buyer_opportunity("Agency Owner", bait_post, require_target_geo=True))

    def test_strict_native_english_gate(self):
        en_post = "We are looking for a remote Head of Growth in the UK or Europe to join our team and build our marketing engine."
        self.assertTrue(is_strictly_native_english("Alex Smith", en_post, en_post))

        translated_card = "Alex Smith\nSee translation\nWe are looking for a remote Head of Growth to join our team."
        self.assertFalse(is_strictly_native_english("Alex Smith", translated_card, en_post))

    def test_end_to_end_evaluation_and_scoring(self):
        now_utc = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)
        post_dt = now_utc - timedelta(hours=2)
        li_id = int(post_dt.timestamp() * 1000) << 22
        url = f"https://www.linkedin.com/feed/update/urn:li:activity:{li_id}/"

        res = evaluate_post(
            text="We are looking for recommendations for an AI workflow automation architect (n8n / Claude) to help our remote UK team streamline CRM handoffs. Drop a comment or DM me!",
            url=url,
            author="Sarah Chen, Founder & CEO",
            company="AcmeAI",
            is_1st_connection=True,
            now_utc=now_utc,
        )
        self.assertTrue(res["passed"])
        self.assertEqual(res["track"], "AI")
        self.assertGreaterEqual(res["suitability_score"], 90.0)
        self.assertLessEqual(len(res["suggested_reply"]), 220)


if __name__ == "__main__":
    unittest.main()
