"""Papermill risk scoring — v1 (current) and v2 (proposed, contained changes)."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def author_display_name(
    first: str | None, middle: str | None, last: str | None, full: str | None
) -> str:
    if full:
        return full.strip()
    parts = [p for p in (first, middle, last) if p]
    return " ".join(parts).strip()


def email_local_part(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    return email.split("@", 1)[0]


def email_has_letters(email: str | None) -> bool:
    return bool(re.search(r"[a-zA-Z]", email_local_part(email)))


def email_is_numeric_only(email: str | None) -> bool:
    local = email_local_part(email)
    return bool(local) and local.isdigit()


def extract_affiliation(model_json: str | None) -> str | None:
    if not model_json:
        return None
    try:
        model = json.loads(model_json)
    except json.JSONDecodeError:
        return None
    authors = model.get("submission", {}).get("authors", [])
    sub = next((a for a in authors if a.get("isSubmittingAuthor")), authors[0] if authors else None)
    if not sub:
        return None
    primary = sub.get("primaryAffiliation")
    if isinstance(primary, dict):
        return primary.get("organisationName") or primary.get("name")
    affiliations = sub.get("affiliations") or []
    if affiliations and isinstance(affiliations[0], dict):
        return affiliations[0].get("name") or affiliations[0].get("organisationName")
    return None


def extract_submitting_author(model_json: str | None) -> tuple[str | None, str | None]:
    if not model_json:
        return None, None
    try:
        model = json.loads(model_json)
    except json.JSONDecodeError:
        return None, None
    authors = model.get("submission", {}).get("authors", [])
    sub = next((a for a in authors if a.get("isSubmittingAuthor")), authors[0] if authors else None)
    if not sub:
        return None, None
    name = author_display_name(sub.get("firstName"), sub.get("middleName"), sub.get("lastName"), sub.get("fullName"))
    email = sub.get("primaryEmail") or sub.get("email")
    return name or None, email or None


def extract_all_authors(model_json: str | None) -> list[dict[str, str]]:
    if not model_json:
        return []
    try:
        model = json.loads(model_json)
    except json.JSONDecodeError:
        return []
    out: list[dict[str, str]] = []
    for a in model.get("submission", {}).get("authors", []):
        name = author_display_name(
            a.get("firstName"), a.get("middleName"), a.get("lastName"), a.get("fullName")
        )
        email = (a.get("primaryEmail") or a.get("email") or "").strip()
        role = "Submitting author" if a.get("isSubmittingAuthor") else "Author"
        org = ""
        primary = a.get("primaryAffiliation")
        if isinstance(primary, dict):
            org = (primary.get("organisationName") or primary.get("name") or "").strip()
        if not org:
            affiliations = a.get("affiliations") or []
            if affiliations and isinstance(affiliations[0], dict):
                org = (affiliations[0].get("name") or affiliations[0].get("organisationName") or "").strip()
        out.append({"name": name, "email": email, "role": role, "org": org})
    return out


def email_similarity_score(author_name: str, email: str | None) -> float:
    if not email or "@" not in email:
        return 0.0
    local_norm = normalize_text(email_local_part(email))
    name_norm = normalize_text(author_name)
    if not name_norm or not local_norm:
        return 0.0
    ratio = SequenceMatcher(None, name_norm, local_norm).ratio()
    tokens = [normalize_text(t) for t in re.split(r"\s+", author_name) if t]
    token_ratios = [SequenceMatcher(None, t, local_norm).ratio() for t in tokens if t]
    return max([ratio * 100, *(r * 100 for r in token_ratios)])


def score_word_doc(status: str | None) -> int:
    if not status or status.lower() == "green":
        return 0
    if status.lower() == "yellow":
        return 10
    if status.lower() == "red":
        return 35
    return 0


def score_device_reuse(article_count: int, affiliation_count: int) -> int:
    score = 0
    if article_count >= 10:
        score += 45
    elif article_count >= 5:
        score += 30
    if affiliation_count >= 3:
        score += 25
    return score


def score_ip_reuse(article_count: int, affiliation_count: int) -> int:
    score = 0
    if article_count >= 10:
        score += 10
    elif article_count >= 5:
        score += 5
    if affiliation_count >= 3:
        score += 10
    return score


def false_positive_adjustments(
    device_article_count: int,
    device_affiliation_count: int,
    language_profile_count: int,
    locale_profile_count: int,
) -> int:
    reduction = 0
    if device_article_count >= 2 and device_affiliation_count == 1:
        reduction -= 20
    if language_profile_count >= 2:
        reduction -= 10
    if locale_profile_count >= 2:
        reduction -= 10
    return max(reduction, -30)


def risk_category(score: int) -> str:
    if score >= 80:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


# --- v1 ---


def score_email_v1(similarity: float) -> int:
    if similarity >= 70:
        return 0
    if similarity >= 40:
        return 5
    if similarity >= 10:
        return 10
    return 25


def score_article_v1(
    *,
    word_doc_status: str | None,
    author_name: str | None,
    author_email: str | None,
    fingerprint_score: int,
    device_articles: int,
    device_aff_count: int,
    language_profiles: int,
    locale_profiles: int,
) -> dict:
    word_score = score_word_doc(word_doc_status)
    sim = email_similarity_score(author_name or "", author_email)
    email_score = score_email_v1(sim)
    fp_adj = false_positive_adjustments(
        device_articles, device_aff_count, language_profiles, locale_profiles
    )
    final_score = max(0, min(100, fingerprint_score + word_score + email_score + fp_adj))
    return {
        "EmailSimilarity": round(sim, 1),
        "WordDocScore": word_score,
        "EmailScore": email_score,
        "SynergyScore": 0,
        "FalsePositiveAdjustment": fp_adj,
        "FinalScore": final_score,
        "RiskCategory": risk_category(final_score),
    }


# --- v2 (proposed, contained) ---


def score_email_v2(similarity: float, email: str | None) -> int:
    """Stronger mismatch weight when local part contains letters; lighter when numeric-only."""
    if email_is_numeric_only(email):
        return 5
    if similarity >= 70:
        return 0
    if similarity >= 40:
        return 10
    if similarity >= 30:
        return 25
    if similarity >= 10:
        return 35
    return 45


def synergy_score_v2(word_doc_status: str | None, similarity: float, email: str | None) -> int:
    """Word doc issue + character-based email mismatch compound signal."""
    status = (word_doc_status or "").lower()
    if status not in ("yellow", "red"):
        return 0
    if similarity >= 40:
        return 0
    if not email_has_letters(email):
        return 0
    return 15


def finalize_v2(
    final_score: int,
    word_doc_status: str | None,
    similarity: float,
    email: str | None,
) -> tuple[int, str]:
    """Red word doc metadata always flags High; low email similarity at least Medium."""
    if (word_doc_status or "").lower() == "red":
        return max(final_score, 80), "High"
    if email_has_letters(email) and similarity < 30:
        final_score = max(final_score, 40)
    return final_score, risk_category(final_score)


def score_article_v2(
    *,
    word_doc_status: str | None,
    author_name: str | None,
    author_email: str | None,
    fingerprint_score: int,
    device_articles: int,
    device_aff_count: int,
    language_profiles: int,
    locale_profiles: int,
) -> dict:
    word_score = score_word_doc(word_doc_status)
    sim = email_similarity_score(author_name or "", author_email)
    email_score = score_email_v2(sim, author_email)
    synergy = synergy_score_v2(word_doc_status, sim, author_email)
    fp_adj = false_positive_adjustments(
        device_articles, device_aff_count, language_profiles, locale_profiles
    )
    raw = fingerprint_score + word_score + email_score + synergy + fp_adj
    final_score, category = finalize_v2(max(0, min(100, raw)), word_doc_status, sim, author_email)
    return {
        "EmailSimilarity": round(sim, 1),
        "WordDocScore": word_score,
        "EmailScore": email_score,
        "SynergyScore": synergy,
        "FalsePositiveAdjustment": fp_adj,
        "FinalScore": final_score,
        "RiskCategory": category,
    }
