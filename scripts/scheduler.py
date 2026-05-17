import asyncio
import argparse
import sys
from common.reddit_scraper import run_keyword_scraper, run_subreddit_scraper
from common.cleaning import deduplicate_merged_csvs
import os

# Repo root: scripts → Reddit_scraper
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data_tmp")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_INTERVAL_MINUTES = 120

GENAI_KEYWORDS = ["transgender","non binary", "agender"]

CONSULTING_KEYWORDS = ["queer", "gay", "lesbian"] #it can be empty

SUBREDDIT_COMMUNITIES = [
    "ainbow",
    "asktransgender",
    "lgbt",
    "trans",
    "transgender",
    "gay",
    "queer",
    "LGBTQ",
    "AskLGBT"
]


def print_global_summary(genai_stats, consulting_stats, sub_stats):
    """Unified clean summary printed after all scrapers run."""

    print("\n========== GLOBAL SUMMARY ==========")

    # GENAI
    print(f"GENAI: {genai_stats['new_posts']} new posts "
          f"(raw: {genai_stats['raw_total']}, unique: {genai_stats['final_total']})")

    # CONSULTING
    print(f"CONSULTING: {consulting_stats['new_posts']} new posts "
          f"(raw: {consulting_stats['raw_total']}, unique: {consulting_stats['final_total']})")

    # SUBREDDITS
    print(f"SUBREDDITS: {sub_stats['new_posts']} new posts "
          f"(raw: {sub_stats['raw_total']})")

    print("====================================\n")

    # Move leaderboard here (GENAI only)
    print("======== TOP 25 SUBREDDITS (GENAI) =========")
    # We extract leaderboard from GENAI file
    try:
        import pandas as pd
        df = pd.read_csv(os.path.join(DATA_DIR, "GENAI_merged.csv"))
        counts = df["community"].value_counts().head(25)
        for i, (sub, count) in enumerate(counts.items(), start=1):
            print(f"{i}. {sub:<25} {count} posts")
    except Exception as e:
        print(f"Could not load GENAI leaderboard: {e}")

    print("============================================\n")


def deduplicate_all_csvs():
    """Run deduplication across all merged CSVs and log the results."""
    print("======= DEDUPLICATION RUN =======")
    try:
        results = deduplicate_merged_csvs(csv_folder=DATA_DIR, quiet=True)
        for result in results:
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
        sleep_secs=10,
    )

    consulting_stats = await run_keyword_scraper(
        label="CONSULTING",
        community="all",
        keywords=CONSULTING_KEYWORDS,
        merged_filename="consulting_kw_merged.csv",
        sleep_secs=5,
    )

    sub_stats = await run_subreddit_scraper(
        communities=SUBREDDIT_COMMUNITIES,
        per_subreddit_limit=250,
    )
    return genai_stats, consulting_stats, sub_stats

async def scheduler(interval_minutes=DEFAULT_INTERVAL_MINUTES):
    """Run scrape cycles continuously with a countdown between runs."""
    while True:
        await run_cycle()
        await countdown_minutes(interval_minutes)


async def run_cycle():
    """Execute one full scrape/dedupe/summary cycle with clean screen."""
    # Clear terminal fully
    sys.stdout.write("\033c")
    sys.stdout.flush()

    # Run scrapers
    genai_stats, consulting_stats, sub_stats = await run_all_once()

    # Deduplicate merged CSVs
    deduplicate_all_csvs()

    # Print unified summary
    print_global_summary(genai_stats, consulting_stats, sub_stats)


async def countdown_minutes(minutes):
    """Display a live countdown in the terminal."""
    # Print first countdown line
    print(f"Next execution in {minutes} minute(s)...")
    remaining = minutes
    while remaining > 0:
        await asyncio.sleep(60)
        remaining -= 1

        # Move cursor UP one line
        sys.stdout.write("\033[F")
        sys.stdout.write("\033[K")   # clear line

        # Rewrite countdown
        print(f"Next execution in {remaining} minute(s)...")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Reddit scraper scheduler.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scrape cycle and exit. Use this for CI or GitHub Actions.",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=DEFAULT_INTERVAL_MINUTES,
        help="Minutes to wait between scheduled runs in continuous mode.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.interval_minutes <= 0:
        raise SystemExit("--interval-minutes must be greater than zero.")

    if args.once:
        asyncio.run(run_cycle())
    else:
        asyncio.run(scheduler(args.interval_minutes))


if __name__ == "__main__":
    main()
