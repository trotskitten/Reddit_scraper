import asyncio
import datetime
import os
import pandas as pd

from common.cleaning import clean_dataframe
from common.io_helpers import merge_clean_save
from common.reddit_client import get_reddit

# Determine repo root: common → scripts → Reddit_scraper
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TEMP_CSV_FOLDER = os.path.join(BASE_DIR, "data_tmp")

# Ensure temp folder exists
os.makedirs(TEMP_CSV_FOLDER, exist_ok=True)

async def run_keyword_scraper(
    *,
    label: str,
    community: str,
    keywords,
    merged_filename: str,
    log_filename: str,
    sleep_secs: int = 5,
):
    """
    Generic keyword-based subreddit scraper:
    - searches each keyword
    - collects posts into a single dataframe
    - cleans, merges, dedupes, logs via shared helpers
    """

    reddit = get_reddit()
    subreddit = await reddit.subreddit(community)

    posts = {
        "Title": [],
        "Text": [],
        "Username": [],
        "ID": [],
        "community": [],
        "Date": [],
        "Time": [],
        "Post URL": [],
    }

    total_raw = 0

    for kw in keywords:
        posts_generator = subreddit.search(kw, sort="new", limit=1000)
        kw_count = 0
        earliest_dt = None

        async for post in posts_generator:
            created_dt = datetime.datetime.fromtimestamp(post.created_utc)

            posts["Date"].append(created_dt.strftime("%d-%m-%Y"))
            posts["Time"].append(created_dt.strftime("%H:%M:%S"))
            posts["Title"].append(post.title)
            posts["Text"].append(post.selftext)
            posts["Username"].append(str(post.author))
            posts["ID"].append(post.id)
            posts["Post URL"].append(post.url)
            posts["community"].append(str(post.subreddit))

            kw_count += 1
            if earliest_dt is None or created_dt < earliest_dt:
                earliest_dt = created_dt

        earliest_str = earliest_dt.strftime("%Y-%m-%d %H:%M:%S") if earliest_dt else "N/A"
        print(f"[{label}] Keyword '{kw}' retrieved: {kw_count} posts (earliest: {earliest_str})")
        total_raw += kw_count

        await asyncio.sleep(sleep_secs)

    await reddit.close()

    df = pd.DataFrame(posts)
    cleaned_df, removed_empty, removed_duplicates = clean_dataframe(df, text_column="Text")

    stats = merge_clean_save(
        df=cleaned_df,
        merged_filename=merged_filename,
        log_filename=log_filename,
    )

    # Override raw_total with actual collected count (pre-cleaning)
    stats["raw_total"] = total_raw

    print(f"========== FINAL {label} SUMMARY ==========")
    print(f"Raw collected posts:          {total_raw}")
    print(f"After clean before dedupe:    {stats['old_total']}")
    print(f"Final unique posts:           {stats['final_total']}")
    print(f"New unique posts added:       {stats['new_posts']}")
    print("=========================================\n")

    return {
        "label": label,
        "raw_total": stats["raw_total"],
        "old_total": stats["old_total"],
        "final_total": stats["final_total"],
        "new_posts": stats["new_posts"],
    }

async def run_subreddit_scraper(
    *,
    communities,
    per_subreddit_limit: int = 250,
):
    """
    Scrape newest posts for multiple subreddits (non-keyword) and merge per subreddit.
    Returns aggregated stats consistent with the orchestrator expectation.
    """

    reddit = get_reddit()

    total_raw = 0
    total_new = 0

    for community in communities:
        stats = await _scrape_single_subreddit(
            reddit=reddit,
            community=community,
            limit=per_subreddit_limit,
        )
        total_raw += stats["raw_count"]
        total_new += stats["new_posts_added"]

    await reddit.close()

    return {
        "label": "SUBREDDITS",
        "raw_total": total_raw,
        "old_total": None,
        "final_total": None,
        "new_posts": total_new,
    }


async def _scrape_single_subreddit(*, reddit, community: str, limit: int):
    """Scrape newest posts from a subreddit and maintain a cleaned merged CSV."""

    subreddit = await reddit.subreddit(community)

    print(f"Scraping newest posts from r/{community} ...")
    posts_generator = subreddit.new(limit=limit)

    posts_dict = {
        "Title": [],
        "Text": [],
        "Username": [],
        "ID": [],
        "community": [],
        "Date": [],
        "Time": [],
        "Post URL": [],
    }

    timestamps = []
    raw_count = 0

    async for post in posts_generator:
        created_dt = datetime.datetime.fromtimestamp(post.created_utc)

        posts_dict["Date"].append(created_dt.strftime("%d-%m-%Y"))
        posts_dict["Time"].append(created_dt.strftime("%H:%M:%S"))
        posts_dict["Title"].append(post.title)
        posts_dict["Text"].append(post.selftext)
        posts_dict["Username"].append(str(post.author))
        posts_dict["ID"].append(post.id)
        posts_dict["Post URL"].append(post.url)
        posts_dict["community"].append(community)

        timestamps.append(created_dt)
        raw_count += 1

    earliest_str = min(timestamps).strftime("%Y-%m-%d %H:%M:%S") if timestamps else "N/A"
    print(f"Retrieved {raw_count} posts from r/{community} (earliest: {earliest_str})")

    merged_file = os.path.join(TEMP_CSV_FOLDER, f"{community}_merged.csv")

    initial_merged_count = 0
    if os.path.exists(merged_file):
        existing_df = pd.read_csv(merged_file)
        initial_merged_count = len(existing_df)
        df = pd.concat([existing_df, pd.DataFrame(posts_dict)], ignore_index=True)
    else:
        df = pd.DataFrame(posts_dict)

    df, removed_empty, removed_duplicates = clean_dataframe(df, text_column="Text")
    after_dedupe = len(df)

    df.to_csv(merged_file, index=False)

    new_posts_added = after_dedupe - initial_merged_count

    print(f"--- Summary for r/{community} ---")
    print(f"Raw posts retrieved:                {raw_count}")
    print(f"Removed empty text posts:           {removed_empty}")
    print(f"Removed duplicate-text posts:       {removed_duplicates}")
    print(f"Posts in merged file (before update): {initial_merged_count}")
    print(f"Posts in merged file (after update):  {after_dedupe}")
    print(f"New posts added to merged file:     {new_posts_added}")
    print("------------------------------------\n")

    return {
        "community": community,
        "raw_count": raw_count,
        "removed_empty": removed_empty,
        "removed_duplicates": removed_duplicates,
        "initial_merged_count": initial_merged_count,
        "final_merged_count": after_dedupe,
        "new_posts_added": new_posts_added,
    }
