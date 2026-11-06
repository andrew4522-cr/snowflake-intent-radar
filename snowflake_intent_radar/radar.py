#!/usr/bin/env python3
"""
========================================================================================
SNOWFLAKE INTENT RADAR — Sub-24h Social Buyer-Intent Scanner via 64-Bit Snowflake Math
Author: Andrew Anderson (BridgingTheAIGap.com)
License: MIT
========================================================================================
LinkedIn and X search filters routinely surface weeks-old posts because of recent comment
activity or boosted threads. `snowflake-intent-radar` solves this mathematically:

1. 64-Bit Snowflake ID Timestamp Decoder (`extract_snowflake_datetime`):
   - Extracts the 64-bit Snowflake ID from LinkedIn (`activity`, `share`, `ugcPost`) and
     X/Twitter (`status`) URLs or URNs.
   - Bit-shifts `(snowflake_id >> 22)` to recover the exact UTC millisecond creation
     timestamp and mathematically verifies `< 24.0h` recency.

2. Buyer-Intent vs. Agency / Job-Seeker Noise Filter (`is_valid_buyer_opportunity`):
   - Rejects 120+ supply-side patterns (`#opentowork`, agency self-promotion, lead-magnet
     "comment X to get Y" bait, podcast promotions, and onsite/US-only restrictions).
   - Captures genuine Founder/Exec Distress (`"anyone recommend"`, `"looking for a fractional"`,
     `"struggling with"`, `"need help automating"`) and Senior Remote Hiring Posts.

3. Strict Native-English Gate (`is_strictly_native_english`):
   - Rejects platform auto-translations (`"See original"`, `"Translated by"`), non-Latin
     scripts, foreign job-post stopwords, and requires English function-word density.

4. 100-Point Suitability Rubric (`compute_suitability_score`):
   - Ranks verified `<24h` opportunities across 1st-Degree Connection priority (+30),
     Active Process Distress (+25), Geography Fit (+30), Decision-Maker Authority (+25),
     Direct Buyer Actionability (+25), Wheelhouse Depth (+20), and Freshness Decay (+15).
========================================================================================
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

TWITTER_EPOCH_MS = 1288834974657

SUPPLY_OR_COMMENTARY_EXCLUSIONS: List[str] = [
    r"\bavailable for hire\b",
    r"\bi['’]?m looking for (?:select )?(?:fractional|opportunities|new clients|my next role|a new role)\b",
    r"\bi am (?:currently )?looking for (?:select )?(?:fractional|opportunities|new clients|my next role|a new role)\b",
    r"\bseeking a fractional or contract\b",
    r"\bopen to work\b",
    r"#opentowork",
    r"\bif you['’]?re hiring\b",
    r"\banyone thinking of hiring (?:him|her|them)\b",
    r"\bopen to interim, fractional or permanent roles\b",
    r"\bi['’]?ve opened up some capacity\b",
    r"\bi only have capacity for\b",
    r"\bhire me\b",
    r"\bi just killed marketing agencies\b",
    r"\bstop paying \$?\d+[,k]*/mo for agencies\b",
    r"\btry it for free\b",
    r"\bdm me ['\"]?[a-z0-9]+['\"]? to get\b",
    r"\bcomment ['\"]?[a-z0-9]+['\"]? and i['’]?ll send\b",
    r"\bcomment ['\"“]?[a-z0-9]+['\"”]? and our team will\b",
    r"\bin this episode\b",
    r"\bnew episode alert\b",
    r"\bep\s*\d+:\b",
    r"\bi['’]?m happy to share that i['’]?m starting a new position\b",
    r"\bweekly job recap\b",
    r"\bstop applying into the void\b",
    r"\bi['’]?m available to support\b",
    r"\bwe provide professional support\b",
    r"\blooking for a fractional [a-z]+\?\s*let['’]?s chat\b",
    r"\blooking for reliable agency collaboration\b",
    r"\bstepping into the role of\b",
    r"\bofficially stepped into\b",
    r"\bkicking off my new role\b",
    r"\bseeking a new role\b",
    r"\bfind (?:my|her|his) next (?:opportunity|role)\b",
    r"#ad\b",
    r"\bopen (?:to|for) freelance\b",
    r"\bactively looking for your next job\b",
    r"\bavailable for freelance\b",
    r"\bcurrently looking for freelance\b",
    r"\bi help businesses\b",
    r"\bhelping businesses grow\b",
    r"\b30-day (?:linkedin|growth|content) challenge\b",
]

HARD_DISQUALIFIERS: List[str] = [
    r"\bmust live in usa\b",
    r"\bus citizens only\b",
    r"\bsecurity clearance required\b",
    r"\binternship\b",
    r"\bintern\b",
    r"\bhybrid\b",
    r"\bon[- ]?site\b",
    r"\bin[- ]office\b",
    r"\bus\s+only\b",
    r"\bu\.s\.\s+only\b",
    r"\bunited states only\b",
    r"\bbased in the us\b",
    r"\bmust be in the us\b",
]

TARGET_GEO_PATTERNS: List[str] = [
    r"\bremote\b",
    r"\bwork from anywhere\b",
    r"\bworldwide\b",
    r"\bglobal\b",
    r"\beurope\b",
    r"\bemea\b",
    r"\buk\b",
    r"\bunited kingdom\b",
    r"\blondon\b",
    r"\bireland\b",
    r"\bdublin\b",
    r"\beu\b",
]

STRONG_BUYER_PATTERNS: List[str] = [
    r"\bwe['’]?re hiring\b",
    r"\bwe are hiring\b",
    r"\bi['’]?m hiring\b",
    r"\bi am hiring\b",
    r"\bmy team is hiring\b",
    r"\bhiring for my team\b",
    r"\bnow hiring\b",
    r"\burgent hire\b",
    r"\burgent hiring\b",
    r"\bhiring for\b",
    r"\bhiring:\b",
    r"\bhiring a\b",
    r"\bhiring an\b",
    r"\b#hiring\b",
    r"\blooking for a\b",
    r"\blooking for an\b",
    r"\bwe['’]?re looking for\b",
    r"\bwe are looking for\b",
    r"\bsearching for a\b",
    r"\blooking to bring on\b",
    r"\blooking to hire\b",
    r"\bopen role\b",
    r"\bopen roles\b",
    r"\bwe need an?\b",
    r"\bjoin our team\b",
    r"\bgrowing our .* team\b",
]

PAIN_COMPLAINT_PATTERNS: List[str] = [
    r"\banyone recommend\b",
    r"\bcan anyone recommend\b",
    r"\brecommend a good\b",
    r"\brecommendations for a\b",
    r"\blooking for recommendations\b",
    r"\bany recommendations for\b",
    r"\bwho do you recommend\b",
    r"\bwould love recommendations\b",
    r"\blooking for someone to\b",
    r"\blooking for someone who can\b",
    r"\blooking for someone with experience\b",
    r"\blooking for a contractor\b",
    r"\blooking for a freelancer\b",
    r"\blooking for a freelance\b",
    r"\bindependent freelance\b",
    r"\blooking for a consultant\b",
    r"\blooking for a fractional\b",
    r"\blooking for a hands-on specialist\b",
    r"\blooking for an agency\b",
    r"\blooking for (?:an?|someone) [^\n.!?]{0,50}\b(?:n8n|make\.com|zapier|hubspot|crm|revops|google ads|meta ads|paid ads|seo|consultant|specialist|expert|freelancer?|partner)\b",
    r"\bwe['’]?re struggling with\b",
    r"\bwe are struggling with\b",
    r"\bstruggling with our\b",
    r"\bfrustrated with our\b",
    r"\bneed help fixing\b",
    r"\bneed help automating\b",
    r"\bneed help with our\b",
    r"\bneed help with\b",
    r"\bcreate systems, tighten ops\b",
]

TRANSLATION_INDICATORS: List[str] = [
    r"\bsee original\b",
    r"\bshow original\b",
    r"\bsee translation\b",
    r"\bshow translation\b",
    r"\btranslated by\b",
    r"\btranslated from\b",
    r"\bver traducci[oó]n\b",
    r"\bvoir la traduction\b",
    r"\b[uü]bersetzung anzeigen\b",
]

FOREIGN_WORD_PATTERNS: List[str] = [
    r"\b(?:estamos|buscando|buscamos|vacante|puesto|nuestro|nuestra|equipo|empresa|contratando|vaga|equipe|trabalho|oportunidade)\b",
    r"\b(?:wir|suchen|stellenangebot|vollzeit|teilzeit|deine|aufgaben|bewerbung|gesch[aä]ftsf[uü]hrer|unser|unserem)\b",
    r"\b(?:nous|recherchons|recrute|poste|cdi|cdd|notre|équipe|candidature|rejoindre|télétravail|entreprise)\b",
]

ENGLISH_FUNCTION_WORDS = {
    "the", "and", "to", "of", "in", "for", "with", "on", "at", "from", "by", "about", "as", "into",
    "we", "our", "you", "your", "are", "is", "this", "that", "who", "will", "work", "team", "role",
    "join", "looking", "hiring", "build", "growth", "marketing", "operations",
}


def extract_snowflake_datetime(url_or_urn: str) -> Optional[datetime]:
    """
    Decode exact UTC creation datetime from a 64-bit LinkedIn (`activity`, `share`, `ugcPost`)
    or X/Twitter (`status`) Snowflake ID.

    Math:
    - LinkedIn Snowflake ID: top 42 bits (`id >> 22`) = Unix epoch milliseconds.
    - X/Twitter Snowflake ID: `(id >> 22) + 1288834974657` = Unix epoch milliseconds.
    """
    li_m = re.search(r"(?:activity|share|ugcPost)[-:](\d{18,20})", url_or_urn or "")
    if li_m:
        try:
            ms = int(li_m.group(1)) >> 22
            dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            if 2015 <= dt.year <= 2035:
                return dt
        except Exception:
            pass

    x_m = re.search(r"status/(\d{18,20})", url_or_urn or "")
    if x_m:
        try:
            ms = (int(x_m.group(1)) >> 22) + TWITTER_EPOCH_MS
            dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            if 2015 <= dt.year <= 2035:
                return dt
        except Exception:
            pass
    return None


def verify_snowflake_recency(
    url_or_urn: str,
    max_hours: float = 24.0,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Verify whether a LinkedIn or X post URL/URN was mathematically created within `max_hours`.
    """
    now = now_utc or datetime.now(timezone.utc)
    dt = extract_snowflake_datetime(url_or_urn)
    if dt is None:
        return {
            "valid_snowflake": False,
            "within_window": False,
            "created_at_utc": None,
            "age_hours": None,
            "age_badge": None,
        }
    age_seconds = max(0.0, (now - dt).total_seconds())
    age_hours = age_seconds / 3600.0
    return {
        "valid_snowflake": True,
        "within_window": age_hours <= max_hours,
        "created_at_utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "age_hours": round(age_hours, 2),
        "age_badge": format_age_badge(dt, now),
    }


def format_age_badge(dt: datetime, now_utc: Optional[datetime] = None) -> str:
    """Return human-readable age badge (e.g., '38m ago' or '4.2h ago')."""
    now = now_utc or datetime.now(timezone.utc)
    secs = max(60.0, (now - dt).total_seconds())
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    hours = secs / 3600.0
    return f"{hours:.1f}h ago"


def is_strictly_native_english(author: str, raw_card_text: str, body_text: str) -> bool:
    """
    Ensure the post is 100% native English and never auto-translated by LinkedIn/X or written in another language.
    """
    card_combined = f"{author or ''}\n{raw_card_text or ''}\n{body_text or ''}"
    body_only = body_text or ""

    for pat in TRANSLATION_INDICATORS:
        if re.search(pat, card_combined, re.I):
            return False

    if re.search(
        r"[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0900-\u097F\u0E00-\u0E7F\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]",
        card_combined,
    ):
        return False

    if re.search(
        r"[ãõçñßäöüåøæłńśźżćęąřčšžđğşÃÕÇÑÄÖÜÅØÆŁŃŚŹŻĆĘĄŘČŠŽĐĞŞ¿¡]",
        card_combined,
    ):
        return False

    for pat in FOREIGN_WORD_PATTERNS:
        if re.search(pat, body_only, re.I):
            return False

    words = {w.lower().strip(".,:;!?()[]\"'") for w in body_only.split()}
    if len(words.intersection(ENGLISH_FUNCTION_WORDS)) < 4:
        return False

    return True


def is_valid_buyer_opportunity(title: str, text: str, require_target_geo: bool = False) -> bool:
    """
    True only if the post is:
    1. Free of all self-promotion, demo, job-seeker, and onsite/US-only disqualifiers.
    2. A genuine buyer hiring request or active founder pain complaint.
    3. When `require_target_geo=True`: explicitly Remote Worldwide / Europe / UK or a borderless founder pain post.
    """
    combined = f"{title or ''}\n{text or ''}"
    for pat in SUPPLY_OR_COMMENTARY_EXCLUSIONS + HARD_DISQUALIFIERS:
        if re.search(pat, combined, re.I):
            return False
    is_pain = any(re.search(pat, combined, re.I) for pat in PAIN_COMPLAINT_PATTERNS)
    is_buyer = any(re.search(pat, combined, re.I) for pat in STRONG_BUYER_PATTERNS)
    if not (is_pain or is_buyer):
        return False
    if require_target_geo:
        has_target_geo = any(re.search(pat, combined, re.I) for pat in TARGET_GEO_PATTERNS)
        return has_target_geo or is_pain
    return True


def is_linkedin_1st_connection(card_text: str) -> bool:
    """Detect whether a LinkedIn post author is a 1st-degree connection from card header lines."""
    lines = [ln.strip() for ln in (card_text or "").splitlines() if ln.strip() and ln.strip() != "\u200b"]
    header_window = "\n".join(lines[:10])
    if re.search(r"(?:•\s*[23](?:nd|rd)\+?|\b[23](?:nd|rd)\s+degree\b)", header_window, re.I):
        return False
    if re.search(r"(?:•\s*1st\b|\b1st\s+degree\b)", header_window, re.I):
        return True
    return False


def is_valid_1st_connection_post(title: str, text: str) -> bool:
    """Validate a <24h post from a 1st-degree LinkedIn connection for buyer intent or active distress."""
    combined = f"{title or ''}\n{text or ''}"
    first_conn_exclusions = [
        r"\bstarted a new role\b",
        r"\bstarting a new position\b",
        r"\bstepping into the role\b",
        r"\bofficially stepped into\b",
        r"\bkicking off my new role\b",
        r"\bcomplete this survey\b",
    ]
    for pat in first_conn_exclusions:
        if re.search(pat, combined, re.I):
            return False
    return is_valid_buyer_opportunity(title, text, require_target_geo=True)


def parse_linkedin_card(card_text: str) -> Tuple[str, str, str]:
    """Parse a LinkedIn SDUI 'Feed post' card into `(author, company, body_text)`."""
    lines = [ln.strip() for ln in (card_text or "").splitlines() if ln.strip() and ln.strip() != "\u200b"]
    if lines and lines[0].lower() == "feed post":
        lines = lines[1:]
    author = lines[0] if lines else "Hiring Lead"
    author = re.sub(r"\s*•.*$", "", author).strip()

    body_start = 1
    headline_lines = []
    for i in range(1, min(len(lines), 8)):
        ln = lines[i]
        if ln in ("Follow", "Connect", "Message", "Join") or re.fullmatch(r"\d+\s*(?:m|h|d|mo|w)\b.*", ln):
            body_start = i + 1
            if i + 1 < len(lines) and lines[i + 1] in ("Follow", "Connect", "Message", "Join"):
                body_start = i + 2
            break
        if not ln.startswith("•"):
            headline_lines.append(ln)

    headline = " | ".join(headline_lines)
    comp = ""
    m_at = re.search(
        r"(?:@|\bat\s+)([A-Z][A-Za-z0-9&.-]{1,22}(?:\s+[A-Z][A-Za-z0-9&.-]{1,22})?)(?:\s*[|·.,•]|$)",
        headline,
    )
    if m_at:
        comp = m_at.group(1).strip()

    body_lines = []
    for ln in lines[body_start:]:
        if ln in ("Like", "Comment", "Repost", "Send"):
            break
        if ln in ("… more", "... more", "…more", "...more", "View job"):
            continue
        body_lines.append(ln)

    return author, comp, " ".join(body_lines).strip()


def parse_x_card(url: str, title: str, text: str) -> Tuple[str, str, str]:
    """Parse an X/Twitter card or search snippet into `(author_label, company, body_text)`."""
    m_url = re.search(r"x\.com/([^/?#]+)/status/", url or "")
    handle = f"@{m_url.group(1)}" if m_url else "@founder"
    display = handle.lstrip("@")
    m_on_x = re.search(r"([A-Za-z0-9_ .'-]{2,32}?)\s+on\s+(?:X|Twitter):", f"{title} {text}")
    if m_on_x:
        cand = m_on_x.group(1).split("|")[-1].strip()
        if cand and len(cand) <= 30:
            display = cand
    author_label = f"{display} ({handle})" if display.lower() != handle.lstrip("@").lower() else handle

    body_text = text or ""
    m_quote = re.search(r'on\s+(?:X|Twitter):\s*"?(.+)', body_text)
    if m_quote:
        raw_q = re.split(r'(?:"\s*/\s*X|\s*\|\s*\d+\s*(?:hours?|mins?|minutes?|days?)\s*ago)', m_quote.group(1))[0]
        body_text = raw_q.strip().strip('"').strip()

    comp = ""
    comp_m = re.search(r"\bat\s+([A-Z][A-Za-z0-9_.-]{2,20})\b", body_text)
    if comp_m:
        comp = comp_m.group(1).strip()

    return author_label, comp, body_text


def classify_track_and_subangle(default_track: str, body_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Classify the opportunity into a single track (`MARKETING`, `AI`, `OPERATIONS`) and proof sub-angle."""
    combined = (body_text or "").lower()

    ai_patterns = [
        r"\bai\b", r"\bagentic\b", r"\bagent\b", r"\bagents\b", r"\bllm\b", r"\bclaude\b",
        r"\bn8n\b", r"\bmake\.com\b", r"\bzapier\b", r"\blangchain\b", r"\bworkflow automation\b",
        r"\bgtm engineer\b", r"\bmcp\b", r"\bautomation\b", r"\bautomating\b", r"\bautomate\b",
    ]
    ops_patterns = [
        r"\bcoo\b", r"\bchief operating officer\b", r"\bhead of operations\b", r"\bdirector of operations\b",
        r"\bvp of operations\b", r"\brevops\b", r"\brevenue operations\b", r"\bchief of staff\b",
        r"\bbizops\b", r"\bbusiness operations\b", r"\boperations\b", r"\bcrm\b", r"\bhubspot\b",
        r"\bsilos\b", r"\bhandoffs\b", r"\btighten ops\b", r"\bcreate systems\b",
    ]
    mkt_patterns = [
        r"\bcmo\b", r"\bchief marketing officer\b", r"\bhead of growth\b", r"\bgrowth marketing\b",
        r"\bvp[,]?\s*marketing\b", r"\bhead of marketing\b", r"\bperformance marketing\b",
        r"\bpaid acquisition\b", r"\bcreator\b", r"\bugc\b", r"\binfluencer\b", r"\bbrand\b",
        r"\bdemand generation\b", r"\bmarketer\b", r"\bcac\b", r"\broas\b", r"\battribution\b",
        r"\bpaid ads\b", r"\bgoogle ads\b", r"\bmeta ads\b", r"\blead generation\b", r"\bmarketing\b",
    ]

    ai_hits = sum(1 for p in ai_patterns if re.search(p, combined))
    ops_hits = sum(1 for p in ops_patterns if re.search(p, combined))
    mkt_hits = sum(1 for p in mkt_patterns if re.search(p, combined))

    if ai_hits + ops_hits + mkt_hits == 0:
        return None, None

    if default_track == "OPERATIONS" and ops_hits >= 1:
        track = "OPERATIONS"
    elif default_track == "AI" and ai_hits >= 1:
        track = "AI"
    elif default_track == "MARKETING" and mkt_hits >= 1:
        track = "MARKETING"
    elif ai_hits >= max(ops_hits, mkt_hits):
        track = "AI"
    elif ops_hits >= max(ai_hits, mkt_hits):
        track = "OPERATIONS"
    else:
        track = "MARKETING"

    sub_map = {
        "AI": "BTAG_PRODUCTION_50PCT_16HRS",
        "OPERATIONS": "EIRCAP_CRO_FUNNEL_10_TO_18",
        "MARKETING": "CULT_BRAND_REVENUE_263",
    }
    return track, sub_map[track]


def compute_suitability_score(
    author_meta: str,
    full_text: str,
    age_hours: float,
    is_fresh: bool = True,
    is_1st_connection: bool = False,
) -> float:
    """
    Multi-Factor Suitability Score (0 - 100 pts):
      0a. 1st-Degree Connection Priority Bonus (+30 pts)
      0b. Help / Recommendation / Process-Distress Boost (+25 pts)
      1.  Geography Fit (+10 to +30 pts): Explicit Remote / Worldwide / UK / Europe
      2.  Decision-Maker Authority (+10 to +25 pts): Individual Founder, C-Suite, VP, Partner, Head-of
      3.  Direct Buyer Actionability (+14 to +25 pts): Direct DM/comment/reply/email CTA
      4.  Core Wheelhouse Depth (+10 to +20 pts): Exact senior role or problem match
      5.  Freshness Bonus (0 to +15 pts): First-mover advantage for posts <6h old
    """
    combined = f"{author_meta or ''} {full_text or ''}".lower()
    score = 30.0 if is_1st_connection else 0.0

    if any(re.search(pat, combined, re.I) for pat in PAIN_COMPLAINT_PATTERNS):
        score += 25.0

    if re.search(r"\b(remote|work from anywhere|worldwide|global|uk|united kingdom|london|europe|emea|dublin|ireland)\b", combined):
        score += 30.0
    else:
        score += 10.0

    if re.search(r"\b(founder|co-founder|cofounder|ceo|coo|cmo|cto|svp|vp|partner|head of|managing director|owner)\b", combined):
        score += 25.0
    elif re.search(r"\b(director|lead|manager|principal)\b", combined):
        score += 15.0
    else:
        score += 10.0

    if re.search(
        r"\b(dm me|send me a dm|drop a comment|reply in the comments|reply if you['’]?re interested|shoot me a dm|anyone recommend|looking for a contractor)\b",
        combined,
    ) or "@" in (full_text or ""):
        score += 25.0
    else:
        score += 14.0

    if re.search(
        r"\b(head of growth|head of marketing|performance marketing|paid acquisition|meta ads|roas|ugc|gtm engineer|workflow automation|ai agent|head of operations|revops|revenue operations|chief of staff|fractional cmo|fractional coo)\b",
        combined,
    ):
        score += 20.0
    else:
        score += 10.0

    score += max(0.0, 15.0 - (age_hours * 0.6))
    if not is_fresh:
        score -= 10.0

    return min(100.0, round(score, 1))


def generate_tailored_response(
    platform: str,
    author: str,
    company: str,
    track: str,
    sub_angle: str,
    body_text: str,
) -> str:
    """Generate an ultra-succinct single-angle public comment/reply (`<= 220` chars, zero em-dashes)."""
    first_token = (author or "there").split()[0].rstrip(".,:")
    greeting = f"Hey {first_token}," if platform == "X" else f"Hi {first_token},"
    comp_short = f" at {company}" if (company and len(company) <= 14) else ""

    xyz_map = {
        "CULT_BRAND_REVENUE_263": "At CULT, I repositioned the brand, driving +263% revenue at a +40% price premium.",
        "BTAG_PRODUCTION_50PCT_16HRS": "At BridgingTheAIGap, I deployed AI automation pipelines, cutting cycle time 50% (-16h/wk).",
        "EIRCAP_CRO_FUNNEL_10_TO_18": "At Eircap, I overhauled CRM routing & handoffs, lifting conversion 10% to 18% (€40M+ rev).",
    }
    hook_map = {
        "MARKETING": "Scaling brand & paid acquisition",
        "AI": "Building production AI agent workflows",
        "OPERATIONS": "Unifying GTM & cross-team ops",
    }
    xyz = xyz_map.get(sub_angle, xyz_map["BTAG_PRODUCTION_50PCT_16HRS"])
    hook = hook_map.get(track, "Solving this bottleneck")
    cta = "Sent a DM!" if platform == "LinkedIn" else "Open to a quick chat?"
    reply = f"{greeting} {hook}{comp_short} is right in my wheelhouse. {xyz} {cta}"
    return reply.replace("—", "-").replace("–", "-")[:220]


def evaluate_post(
    text: str,
    url: str = "",
    author: str = "Founder",
    company: str = "",
    platform: str = "LinkedIn",
    is_1st_connection: bool = False,
    max_hours: float = 24.0,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    End-to-end evaluation pipeline for a social post across all Snowflake, Native-English,
    Buyer-Intent, Track-Classification, and 100-Point Suitability gates.
    """
    snowflake_info = verify_snowflake_recency(url, max_hours=max_hours, now_utc=now_utc) if url else {
        "valid_snowflake": False,
        "within_window": True,
        "created_at_utc": None,
        "age_hours": 1.0,
        "age_badge": "1.0h ago",
    }
    native_en = is_strictly_native_english(author, author, text)
    buyer_ok = is_valid_buyer_opportunity(author, text, require_target_geo=True)
    track, sub_angle = classify_track_and_subangle("AI", text)
    age_hrs = snowflake_info["age_hours"] if snowflake_info["age_hours"] is not None else 1.0

    score = compute_suitability_score(
        author_meta=author,
        full_text=text,
        age_hours=age_hrs,
        is_fresh=True,
        is_1st_connection=is_1st_connection,
    ) if (native_en and buyer_ok and track) else 0.0

    passed = bool(
        (not url or snowflake_info["within_window"])
        and native_en
        and buyer_ok
        and track is not None
        and score >= 40.0
    )

    reply = (
        generate_tailored_response(platform, author, company, track or "AI", sub_angle or "BTAG_PRODUCTION_50PCT_16HRS", text)
        if passed
        else ""
    )

    return {
        "passed": passed,
        "snowflake": snowflake_info,
        "native_english": native_en,
        "valid_buyer_intent": buyer_ok,
        "track": track,
        "sub_angle": sub_angle,
        "suitability_score": score,
        "suggested_reply": reply,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="snowflake-intent-radar",
        description="Sub-24h Social Buyer-Intent Scanner via 64-Bit Snowflake ID Math",
    )
    parser.add_argument("--decode", metavar="URL_OR_URN", help="Decode a LinkedIn or X URL/URN into its exact UTC Snowflake timestamp")
    parser.add_argument("--evaluate", metavar="POST_TEXT", help="Evaluate a post text through all buyer-intent, native-English, and 100-pt rubric gates")
    parser.add_argument("--url", default="", help="Optional post URL for Snowflake verification with --evaluate")
    parser.add_argument("--author", default="Jane Doe, Founder & CEO", help="Optional author headline for --evaluate")
    parser.add_argument("--max-hours", type=float, default=24.0, help="Maximum post age in hours (default 24.0)")

    args = parser.parse_args(argv)

    if args.decode:
        res = verify_snowflake_recency(args.decode, max_hours=args.max_hours)
        print(json.dumps(res, indent=2))
        return 0

    if args.evaluate:
        res = evaluate_post(
            text=args.evaluate,
            url=args.url,
            author=args.author,
            max_hours=args.max_hours,
        )
        print(json.dumps(res, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
