import asyncio
import sys
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import aiohttp
import pandas as pd

# =========================
# PATHS / CONFIG
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(__file__)) if "__file__" in globals() else os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data_tmp")
os.makedirs(DATA_DIR, exist_ok=True)

GENAI_KEYWORDS = ["transgender", "non binary", "agender"]
CONSULTING_KEYWORDS = ["queer", "gay", "lesbian"]  # can be empty

SUBREDDIT_COMMUNITIES = sorted(set([
    "ainbow",
    "asktransgender",
    "lgbt",
    "trans",
    "transgender",
    "gay",
    "queer",
    "lgbtq",
    "asklgbt",
]))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RedditResearchScraper/1.0"

# =========================
# HELPERS
# =========================

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

def unix_to_iso(ts):
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return None

def normalize_post(post_data):
    """Normalize Reddit post JSON into a flat dict."""
    return {
        "id": post_data.get("id"),
        "title": post_data.get("title"),
        "selftext": post_data.get("selftext"),
        "subreddit": post_data.get("subreddit"),
        "community": post_data.get("subreddit"),  # kept for compatibility with your leaderboard
        "author": post_data.get("author"),
        "score": post_data.get("score"),
        "num_comments": post_data.get("num_comments"),
        "created_utc": post_data.get("created_utc"),
        "created_iso": unix_to_iso(post_data.get("created_utc")),
        "url": post_data.get("url"),
        "permalink": f"https://www.reddit.com{post_data.get('permalink', '')}",
        "over_18": post_data.get("over_18"),
        "is_self": post_data.get("is_self"),
        "scraped_at": utc_now_iso(),
    }

def safe_read_csv(path):
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def append_and_merge_csv(new_df, merged_path):
    """Append new rows to an existing merged CSV, then deduplicate."""
    old_df = safe_read_csv(merged_path)

    if old_df.empty and new_df.empty:
        final_df = pd.DataFrame()
    elif old_df.empty:
        final_df = new_df.copy()
    elif new_df.empty:
        final_df = old_df.copy()
    else:
        final_df = pd.concat([old_df, new_df], ignore_index=True)

    if not final_df.empty:
        final_df = deduplicate_dataframe(final_df)
        final_df.to_csv(merged_path, index=False)

    return old_df, final_df

def deduplicate_dataframe(df):
    """Deduplicate using best available keys."""
    if df.empty:
        return df

    df = df.copy()

    # Prefer ID if present
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"], keep="first")

    # Fallback / extra safety
    fallback_cols = [c for c in ["permalink", "url", "title", "selftext"] if c in df.columns]
    if fallback_cols:
        df = df.drop_duplicates(subset=fallback_cols, keep="first")

    return df.reset_index(drop=True)

def deduplicate_merged_csvs(csv_folder, quiet=True):
    """Deduplicate all CSVs in a folder and return results summary."""
    results = []

    for filename in os.listdir(csv_folder):
        if not filename.lower().endswith(".csv"):
            continue

        path = os.path.join(csv_folder, filename)

        try:
            df = pd.read_csv(path)
            old_total = len(df)

            df = deduplicate_dataframe(df)
            new_total = len(df)

            df.to_csv(path, index=False)

            result = {
                "filename": filename,
                "old_total": old_total,
                "new_total": new_total,
            }
            results.append(result)

            if not quiet:
                print(f"{filename}: {old_total} -> {new_total}")

        except Exception as e:
            results.append({
                "filename": filename,
                "old_total": 0,
                "new_total": 0,
                "error": str(e),
            })
            if not quiet:
                print(f"{filename}: failed ({e})")

    return results

# =========================
# REDDIT FETCHING
# =========================

async def fetch_json(session, url, params=None, retries=3, sleep_secs=2):
    """Fetch JSON with basic retry handling."""
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, retries + 1):
        try:
            async with session.get(url, headers=headers, params=params, timeout=30) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status in (429, 500, 502, 503, 504):
                    if attempt < retries:
                        await asyncio.sleep(sleep_secs * attempt)
                        continue
                    print(f"Request failed after retries: {url} [status {resp.status}]")
                    return None
                else:
                    text = await resp.text()
                    print(f"Request failed: {url} [status {resp.status}] {text[:200]}")
                    return None
        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(sleep_secs * attempt)
            else:
                print(f"Request exception for {url}: {e}")
                return None

async def fetch_search_results(session, query, limit_total=250, sleep_secs=2):
    """
    Search Reddit sitewide for a query using public JSON endpoint.
    Paginates with 'after'.
    """
    url = "https://www.reddit.com/search.json"
    posts = []
    after = None

    while len(posts) < limit_total:
        batch_limit = min(100, limit_total - len(posts))
        params = {
            "q": query,
            "sort": "new",
            "limit": batch_limit,
            "restrict_sr": "false",
            "type": "link",
            "raw_json": 1,
        }
        if after:
            params["after"] = after

        data = await fetch_json(session, url, params=params)
        if not data:
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        for child in children:
            if child.get("kind") == "t3":
                posts.append(normalize_post(child.get("data", {})))

        after = data.get("data", {}).get("after")
        if not after:
            break

        await asyncio.sleep(sleep_secs)

    return posts

async def fetch_subreddit_new(session, subreddit, limit_total=250, sleep_secs=2):
    """
    Fetch newest posts from a subreddit using public JSON endpoint.
    """
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    posts = []
    after = None

    while len(posts) < limit_total:
        batch_limit = min(100, limit_total - len(posts))
        params = {
            "limit": batch_limit,
            "raw_json": 1,
        }
        if after:
            params["after"] = after

        data = await fetch_json(session, url, params=params)
        if not data:
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        for child in children:
            if child.get("kind") == "t3":
                posts.append(normalize_post(child.get("data", {})))

        after = data.get("data", {}).get("after")
        if not after:
            break

        await asyncio.sleep(sleep_secs)

    return posts

# =========================
# SCRAPER FUNCTIONS
# =========================

async def run_keyword_scraper(label, community, keywords, merged_filename, sleep_secs=5, limit_per_keyword=250):
    """
    Search Reddit for each keyword, merge, deduplicate, save, and return stats.
    """
    if not keywords:
        return {"new_posts": 0, "raw_total": 0, "final_total": 0}

    print(f"======= {label} KEYWORD SCRAPER =======")
    print(f"Keywords: {keywords}")
    print(f"Community: {community}")
    print()

    all_posts = []

    async with aiohttp.ClientSession() as session:
        for kw in keywords:
            print(f"[{label}] Searching keyword: {kw}")
            posts = await fetch_search_results(
                session=session,
                query=kw,
                limit_total=limit_per_keyword,
                sleep_secs=sleep_secs,
            )

            # tag keyword origin
            for post in posts:
                post["search_keyword"] = kw
                post["search_label"] = label

            print(f"[{label}] Retrieved {len(posts)} raw posts for '{kw}'")
            all_posts.extend(posts)

            await asyncio.sleep(sleep_secs)

    raw_total = len(all_posts)
    new_df = pd.DataFrame(all_posts)
    merged_path = os.path.join(DATA_DIR, merged_filename)

    old_df, final_df = append_and_merge_csv(new_df, merged_path)

    old_total = len(old_df)
    final_total = len(final_df)
    new_posts = max(final_total - old_total, 0)

    print(f"[{label}] Raw total this run: {raw_total}")
    print(f"[{label}] Previous merged total: {old_total}")
    print(f"[{label}] Final merged unique total: {final_total}")
    print(f"[{label}] New unique posts added: {new_posts}")
    print("=====================================\n")

    return {
        "new_posts": new_posts,
        "raw_total": raw_total,
        "final_total": final_total,
    }

async def run_subreddit_scraper(communities, per_subreddit_limit=250, sleep_secs=2):
    """
    Fetch newest posts from a list of subreddits, merge into one CSV, deduplicate, return stats.
    """
    print("======= SUBREDDIT SCRAPER =======")
    print(f"Communities: {communities}")
    print()

    all_posts = []

    async with aiohttp.ClientSession() as session:
        for sub in communities:
            print(f"[SUBREDDIT] Fetching /r/{sub}")
            posts = await fetch_subreddit_new(
                session=session,
                subreddit=sub,
                limit_total=per_subreddit_limit,
                sleep_secs=sleep_secs,
            )

            for post in posts:
                post["source_type"] = "subreddit"
                post["source_community"] = sub

            print(f"[SUBREDDIT] Retrieved {len(posts)} raw posts from /r/{sub}")
            all_posts.extend(posts)

            await asyncio.sleep(sleep_secs)

    raw_total = len(all_posts)
    new_df = pd.DataFrame(all_posts)
    merged_path = os.path.join(DATA_DIR, "subreddits_merged.csv")

    old_df, final_df = append_and_merge_csv(new_df, merged_path)

    old_total = len(old_df)
    final_total = len(final_df)
    new_posts = max(final_total - old_total, 0)

    print(f"[SUBREDDIT] Raw total this run: {raw_total}")
    print(f"[SUBREDDIT] Previous merged total: {old_total}")
    print(f"[SUBREDDIT] Final merged unique total: {final_total}")
    print(f"[SUBREDDIT] New unique posts added: {new_posts}")
    print("=================================\n")

    return {
        "new_posts": new_posts,
        "raw_total": raw_total,
        "final_total": final_total,
    }

# =========================
# SUMMARY / ORCHESTRATION
# =========================

def print_global_summary(genai_stats, consulting_stats, sub_stats):
    """Unified clean summary printed after all scrapers run."""
    print("\n========== GLOBAL SUMMARY ==========")

    print(
        f"GENAI: {genai_stats.get('new_posts', 0)} new posts "
        f"(raw: {genai_stats.get('raw_total', 0)}, unique: {genai_stats.get('final_total', 0)})"
    )

    print(
        f"CONSULTING: {consulting_stats.get('new_posts', 0)} new posts "
        f"(raw: {consulting_stats.get('raw_total', 0)}, unique: {consulting_stats.get('final_total', 0)})"
    )

    print(
        f"SUBREDDITS: {sub_stats.get('new_posts', 0)} new posts "
        f"(raw: {sub_stats.get('raw_total', 0)}, unique: {sub_stats.get('final_total', 0)})"
    )

    print("====================================\n")

    print("======== TOP 25 SUBREDDITS (GENAI) =========")
    try:
        path = os.path.join(DATA_DIR, "GENAI_merged.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            if "community" in df.columns and not df.empty:
                counts = df["community"].value_counts().head(25)
                for i, (sub, count) in enumerate(counts.items(), start=1):
                    print(f"{i}. {sub:<25} {count} posts")
            else:
                print("GENAI leaderboard unavailable: empty file or missing 'community' column.")
        else:
            print("GENAI leaderboard unavailable: file not found.")
    except Exception as e:
        print(f"Could not load GENAI leaderboard: {e}")

    print("============================================\n")

def deduplicate_all_csvs():
    """Run deduplication across all merged CSVs and log the results."""
    print("======= DEDUPLICATION RUN =======")
    try:
        results = deduplicate_merged_csvs(csv_folder=DATA_DIR, quiet=True)
        for result in results:
            if "error" in result:
                print(f"{result['filename']}: failed ({result['error']})")
            else:
                delta = result["old_total"] - result["new_total"]
                print(f"{result['filename']}: {result['old_total']} -> {result['new_total']} (-{delta})")
    except Exception as e:
        print(f"Deduplication failed: {e}")
    print("=================================\n")

async def run_all_once():
    """Run all scrapers sequentially and return their summary dicts."""
    genai_stats = await run_keyword_scraper(
        label="GENAI",
        community="all",
        keywords=GENAI_KEYWORDS,
        merged_filename="GENAI_merged.csv",
        sleep_secs=3,
        limit_per_keyword=250,
    )

    if CONSULTING_KEYWORDS:
        consulting_stats = await run_keyword_scraper(
            label="CONSULTING",
            community="all",
            keywords=CONSULTING_KEYWORDS,
            merged_filename="consulting_kw_merged.csv",
            sleep_secs=3,
            limit_per_keyword=250,
        )
    else:
        consulting_stats = {
            "new_posts": 0,
            "raw_total": 0,
            "final_total": 0,
        }
        print("CONSULTING scraper skipped: no keywords provided.\n")

    sub_stats = await run_subreddit_scraper(
        communities=SUBREDDIT_COMMUNITIES,
        per_subreddit_limit=250,
        sleep_secs=2,
    )

    return genai_stats, consulting_stats, sub_stats

async def countdown_minutes(minutes):
    """Display a live countdown in the terminal."""
    print(f"Next execution in {minutes} minute(s)...")
    remaining = minutes
    while remaining > 0:
        await asyncio.sleep(60)
        remaining -= 1
        sys.stdout.write("\033[F")
        sys.stdout.write("\033[K")
        print(f"Next execution in {remaining} minute(s)...")

async def run_cycle():
    """Execute one full scrape/dedupe/summary cycle with clean screen."""
    sys.stdout.write("\033c")
    sys.stdout.flush()

    genai_stats, consulting_stats, sub_stats = await run_all_once()
    deduplicate_all_csvs()
    print_global_summary(genai_stats, consulting_stats, sub_stats)

async def scheduler():
    """Main hourly loop with clean terminal + countdown refresh."""
    await run_cycle()

    user_choice = input("Run hourly cycles continuously? [y/N]: ").strip().lower()
    if user_choice != "y":
        print("Scheduler finished after single run.")
        return

    while True:
        await countdown_minutes(60)
        await run_cycle()

if __name__ == "__main__":
    # Use run_cycle() for a single run, scheduler() for continuous mode
    asyncio.run(run_cycle())
    # asyncio.run(scheduler())
