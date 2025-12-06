import asyncio
import sys
from common.reddit_scraper import run_keyword_scraper, run_subreddit_scraper
from common.cleaning import deduplicate_merged_csvs

# Repo root: scripts → Reddit_scraper
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data_tmp")
os.makedirs(DATA_DIR, exist_ok=True)

GENAI_KEYWORDS = [
    "ai bot",
    "gen ai",
    "ai tools",
    "chatgpt",
    "genai",
    "generative artificial intelligence",
    "ai chat",
    "generative ai",
]

CONSULTING_KEYWORDS = ["consulting", "consultant", "consultancy"]

SUBREDDIT_COMMUNITIES = [
    "ChatGPT",
    "consulting",
    "AiAssisted",
    "antiai",
    "GeminiAI",
    "GenAI4all",
    "SideProject",
    "ChatGPTcomplaints",
    "ChatGPTPro",
    "ChatGPTJailbreak",
    "AI_Agents",
    "generativeAI",
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
        log_filename="GENAI_log.csv",
        sleep_secs=10,
    )

    consulting_stats = await run_keyword_scraper(
        label="CONSULTING",
        community="all",
        keywords=CONSULTING_KEYWORDS,
        merged_filename="consulting_kw_merged.csv",
        log_filename="consulting_log.csv",
        sleep_secs=5,
    )

    sub_stats = await run_subreddit_scraper(
        communities=SUBREDDIT_COMMUNITIES,
        per_subreddit_limit=250,
    )
    return genai_stats, consulting_stats, sub_stats

async def scheduler():
    """Main hourly loop with clean terminal + countdown refresh."""
    # First run
    await run_cycle()

    # Ask once whether to continue hourly
    user_choice = input("Run hourly cycles continuously? [y/N]: ").strip().lower()
    if user_choice != "y":
        print("Scheduler finished after single run.")
        return

    # Continuous hourly loop
    while True:
        await countdown_minutes(60)
        await run_cycle()


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


if __name__ == "__main__":
    asyncio.run(run_cycle())
