"""
Candidate search script for formal verification engineer role.

Uses LinkedIn's Voyager API directly with cookie authentication
to search for candidates matching the job description.
"""

import json
import logging
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# LinkedIn Voyager API headers
HEADERS = {
    "Accept": "application/vnd.linkedin.normalized+json+2.1",
    "x-li-lang": "en_US",
    "x-restli-protocol-version": "2.0.0",
    "x-li-track": '{"clientVersion":"1.13.8","mpVersion":"1.13.8","osName":"web","timezoneOffset":-8,"deviceFormFactor":"DESKTOP","mpName":"voyager-web","displayDensity":1}',
}

# Search queries targeting different aspects of the job description
SEARCH_QUERIES = [
    "formal verification floating point engineer",
    "formal verification FMAC datapath",
    "IEEE 754 formal verification",
    "VC Formal floating point verification",
    "formal verification AI accelerator arithmetic",
    "SystemVerilog assertions formal verification datapath",
    "formal verification GPU arithmetic datapath",
    "JasperGold formal verification floating point",
    "floating point divider verification",
    "formal verification CPU arithmetic pipeline",
    "formal property verification IEEE 754",
    "RTL formal verification arithmetic unit",
]


def create_session(cookie: str) -> requests.Session:
    """Create authenticated requests session."""
    session = requests.Session()
    session.cookies.set("li_at", cookie, domain=".linkedin.com")
    session.headers.update(HEADERS)
    # Fetch CSRF token
    try:
        resp = session.get("https://www.linkedin.com/voyager/api/me", timeout=15)
        csrf = session.cookies.get("JSESSIONID", "").strip('"')
        if csrf:
            session.headers["csrf-token"] = csrf
    except Exception as e:
        logger.warning(f"Could not fetch CSRF token: {e}")
    return session


def search_people(session: requests.Session, keywords: str, start: int = 0, count: int = 10) -> list[dict]:
    """
    Search LinkedIn for people matching keywords using Voyager API.

    Returns list of candidate dicts.
    """
    params = {
        "decorationId": "com.linkedin.voyager.dash.deco.search.SearchClusterCollection-175",
        "origin": "GLOBAL_SEARCH_HEADER",
        "q": "all",
        "query": f"(keywords:{keywords},resultType:(PEOPLE))",
        "start": start,
        "count": count,
    }

    try:
        resp = session.get(
            "https://www.linkedin.com/voyager/api/graphql",
            params={
                "queryId": "voyagerSearchDashClusters.b0928897b71bd00a5a7291755dcd64f0",
                "variables": f"(start:{start},origin:GLOBAL_SEARCH_HEADER,query:(keywords:{keywords},flagshipSearchIntent:SEARCH_SRP,queryParameters:List((key:resultType,value:List(PEOPLE))),includeFiltersInResponse:false))",
            },
            timeout=20,
        )
    except Exception as e:
        logger.warning(f"Search request failed: {e}")
        return []

    if resp.status_code == 429:
        logger.warning("Rate limited, waiting 30s...")
        time.sleep(30)
        return []

    if resp.status_code != 200:
        # Try alternate API endpoint
        return search_people_alt(session, keywords, start, count)

    results = []
    try:
        data = resp.json()
        included = data.get("included", [])

        for item in included:
            entity_type = item.get("$type", "")
            if "MiniProfile" in entity_type or "Profile" in entity_type:
                public_id = item.get("publicIdentifier") or item.get("publicId", "")
                first = item.get("firstName", "")
                last = item.get("lastName", "")
                headline = item.get("occupation", "") or item.get("headline", "")
                location = item.get("locationName", "") or item.get("geoLocationName", "")

                if public_id and (first or last):
                    results.append({
                        "name": f"{first} {last}".strip(),
                        "headline": headline,
                        "location": location,
                        "profile_url": f"https://www.linkedin.com/in/{public_id}/",
                        "username": public_id,
                    })
    except Exception as e:
        logger.warning(f"Error parsing search results: {e}")

    return results


def search_people_alt(session: requests.Session, keywords: str, start: int = 0, count: int = 10) -> list[dict]:
    """
    Alternate search endpoint using blended search.
    """
    try:
        resp = session.get(
            "https://www.linkedin.com/voyager/api/search/blended",
            params={
                "keywords": keywords,
                "origin": "GLOBAL_SEARCH_HEADER",
                "q": "all",
                "start": start,
                "count": count,
                "filters": "List(resultType->PEOPLE)",
            },
            timeout=20,
        )
    except Exception as e:
        logger.warning(f"Alt search request failed: {e}")
        return []

    if resp.status_code != 200:
        logger.warning(f"Alt search returned {resp.status_code}")
        return []

    results = []
    try:
        data = resp.json()
        elements = data.get("data", {}).get("elements", [])

        for cluster in elements:
            for el in cluster.get("elements", []):
                title = el.get("title", {}).get("text", "")
                headline = el.get("headline", {}).get("text", "")
                subline = el.get("subline", {}).get("text", "")
                nav_url = el.get("navigationUrl", "")

                # Extract username from URL
                username = ""
                if "/in/" in nav_url:
                    username = nav_url.split("/in/")[1].split("?")[0].rstrip("/")

                if title and username:
                    results.append({
                        "name": title,
                        "headline": headline,
                        "location": subline,
                        "profile_url": f"https://www.linkedin.com/in/{username}/",
                        "username": username,
                    })
    except Exception as e:
        logger.warning(f"Error parsing alt search results: {e}")

    # Also check included entities
    try:
        data = resp.json()
        included = data.get("included", [])
        seen_usernames = {r["username"] for r in results}

        for item in included:
            entity_type = item.get("$type", "")
            if "MiniProfile" in entity_type:
                public_id = item.get("publicIdentifier", "")
                first = item.get("firstName", "")
                last = item.get("lastName", "")
                headline = item.get("occupation", "") or item.get("headline", "")
                location = item.get("locationName", "") or item.get("geoLocationName", "")

                if public_id and public_id not in seen_usernames and (first or last):
                    results.append({
                        "name": f"{first} {last}".strip(),
                        "headline": headline,
                        "location": location,
                        "profile_url": f"https://www.linkedin.com/in/{public_id}/",
                        "username": public_id,
                    })
                    seen_usernames.add(public_id)
    except Exception:
        pass

    return results


def search_people_typeahead(session: requests.Session, keywords: str) -> list[dict]:
    """
    Use typeahead/autocomplete API as another search method.
    """
    try:
        resp = session.get(
            "https://www.linkedin.com/voyager/api/search/dash/typeahead",
            params={
                "decorationId": "com.linkedin.voyager.dash.deco.search.SearchAutoComplete-17",
                "query": keywords,
                "type": "PEOPLE",
            },
            timeout=15,
        )
    except Exception as e:
        logger.debug(f"Typeahead request failed: {e}")
        return []

    if resp.status_code != 200:
        return []

    results = []
    try:
        data = resp.json()
        included = data.get("included", [])
        for item in included:
            if "MiniProfile" in item.get("$type", ""):
                public_id = item.get("publicIdentifier", "")
                first = item.get("firstName", "")
                last = item.get("lastName", "")
                headline = item.get("occupation", "")

                if public_id and (first or last):
                    results.append({
                        "name": f"{first} {last}".strip(),
                        "headline": headline,
                        "location": "",
                        "profile_url": f"https://www.linkedin.com/in/{public_id}/",
                        "username": public_id,
                    })
    except Exception:
        pass

    return results


def score_candidate(candidate: dict) -> int:
    """
    Score a candidate based on relevance to the JD.
    Higher score = stronger match.
    """
    score = 0
    text = f"{candidate.get('name', '')} {candidate.get('headline', '')} {candidate.get('about', '')}".lower()

    # Also check experiences if available
    for exp in candidate.get("experiences", []):
        text += f" {exp.get('position_title', '')} {exp.get('description', '')} {exp.get('institution_name', '')}".lower()

    # Must-have signals (high weight)
    must_have_terms = {
        "formal verification": 15,
        "floating point": 12,
        "floating-point": 12,
        "ieee 754": 15,
        "fmac": 15,
        "f-mac": 15,
        "fused multiply": 12,
        "divider": 8,
        "datapath": 10,
        "data path": 10,
        "vc formal": 12,
        "jaspergold": 10,
        "jasper gold": 10,
        "jasper": 6,
        "synopsys": 5,
        "systemverilog": 8,
        "sva": 8,
        "assertions": 6,
        "tapeout": 10,
        "tape-out": 10,
        "tape out": 10,
        "ai accelerator": 10,
        "gpu": 5,
        "cpu": 4,
        "dsp": 4,
        "arithmetic": 8,
        "rounding mode": 12,
        "golden model": 10,
        "reference model": 8,
        "srt": 8,
        "formal": 6,
        "verification": 4,
    }

    for term, weight in must_have_terms.items():
        if term in text:
            score += weight

    # Nice-to-have signals (lower weight)
    nice_to_have_terms = {
        "equivalence checking": 5,
        "onespin": 5,
        "siemens eda": 3,
        "questa formal": 5,
        "cadence": 3,
        "integer alu": 5,
        "fixed-point": 4,
        "mixed-precision": 5,
        "mixed precision": 5,
        "temporal logic": 5,
        "patent": 3,
        "published": 3,
        "mips": 3,
        "infinite precision": 5,
        "bit-accurate": 5,
        "bit accurate": 5,
        "rtl": 3,
        "asic": 3,
        "silicon": 3,
        "chip": 2,
        "processor": 2,
        "accelerator": 4,
        "neural": 2,
        "ml": 2,
        "machine learning": 2,
    }

    for term, weight in nice_to_have_terms.items():
        if term in text:
            score += weight

    return score


def main():
    cookie = os.environ.get("LINKEDIN_COOKIE")
    if not cookie:
        print("ERROR: LINKEDIN_COOKIE not set in environment or .env")
        return

    print("=" * 70)
    print("CANDIDATE SEARCH: Formal Verification Engineer (FP Datapath / AI Accel)")
    print("=" * 70)

    # Create authenticated session
    print("\nAuthenticating with LinkedIn cookie...")
    session = create_session(cookie)

    # Quick auth check
    try:
        me_resp = session.get("https://www.linkedin.com/voyager/api/me", timeout=15)
        if me_resp.status_code == 200:
            me_data = me_resp.json()
            my_name = me_data.get("miniProfile", {}).get("firstName", "User")
            print(f"Authenticated as: {my_name}")
        else:
            print(f"Warning: Auth check returned {me_resp.status_code}, continuing anyway...")
    except Exception as e:
        print(f"Warning: Could not verify auth: {e}, continuing...")

    all_candidates = {}  # keyed by profile_url to dedupe

    # Run searches
    for i, query in enumerate(SEARCH_QUERIES):
        print(f"\n[{i+1}/{len(SEARCH_QUERIES)}] Searching: '{query}'")

        # Primary search
        results = search_people(session, query, start=0, count=10)
        if not results:
            results = search_people_alt(session, query, start=0, count=10)

        # Also try typeahead for additional results
        typeahead_results = search_people_typeahead(session, query)
        all_results = results + typeahead_results

        new_count = 0
        for r in all_results:
            url = r["profile_url"]
            if url not in all_candidates:
                all_candidates[url] = r
                new_count += 1

        print(f"   Found {len(all_results)} results, {new_count} new (total unique: {len(all_candidates)})")

        # Respect rate limits
        if i < len(SEARCH_QUERIES) - 1:
            time.sleep(3)

        # Stop early if we have plenty
        if len(all_candidates) >= 60:
            print(f"   Collected enough candidates ({len(all_candidates)}), stopping search phase.")
            break

    print(f"\nTotal unique candidates found: {len(all_candidates)}")

    if not all_candidates:
        print("\nNo candidates found. The API endpoints may have changed or auth may be invalid.")
        print("Trying a direct HTML scrape approach as fallback...")
        all_candidates = fallback_html_search(session)

    # Score candidates based on available info
    print("Scoring candidates by relevance...")
    scored = []
    for url, cand in all_candidates.items():
        cand["relevance_score"] = score_candidate(cand)
        scored.append(cand)

    # Sort by score descending
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)

    # Take top 25
    top_candidates = scored[:25]

    # Output results
    print("\n" + "=" * 70)
    print(f"TOP {len(top_candidates)} CANDIDATES (sorted by relevance)")
    print("=" * 70)

    for i, cand in enumerate(top_candidates, 1):
        print(f"\n--- Candidate {i} ---")
        print(f"  Name:     {cand['name']}")
        print(f"  Headline: {cand['headline']}")
        print(f"  Location: {cand['location']}")
        print(f"  Profile:  {cand['profile_url']}")
        print(f"  Score:    {cand['relevance_score']}")

    # Save full results to JSON
    output_path = "candidate_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "job_title": "Formal Verification Engineer - FP Datapath / AI Accelerator",
                "total_searched": len(all_candidates),
                "top_candidates": top_candidates,
                "all_candidates": scored,
            },
            f,
            indent=2,
        )
    print(f"\nFull results saved to {output_path}")


def fallback_html_search(session: requests.Session) -> dict:
    """
    Fallback: scrape LinkedIn search HTML pages directly.
    """
    import re

    all_candidates = {}
    queries = SEARCH_QUERIES[:6]  # Use fewer queries for fallback

    for query in queries:
        try:
            resp = session.get(
                "https://www.linkedin.com/search/results/people/",
                params={"keywords": query, "origin": "GLOBAL_SEARCH_HEADER"},
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                },
                timeout=20,
            )
            if resp.status_code != 200:
                continue

            html = resp.text
            # Extract profile URLs from HTML
            profile_pattern = r'href="https://www\.linkedin\.com/in/([^"/?]+)'
            matches = re.findall(profile_pattern, html)

            for username in set(matches):
                url = f"https://www.linkedin.com/in/{username}/"
                if url not in all_candidates:
                    all_candidates[url] = {
                        "name": username.replace("-", " ").title(),
                        "headline": "",
                        "location": "",
                        "profile_url": url,
                        "username": username,
                    }

            time.sleep(2)
        except Exception as e:
            logger.warning(f"Fallback search error: {e}")
            continue

    return all_candidates


if __name__ == "__main__":
    main()
