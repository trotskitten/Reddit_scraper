import os
import pandas as pd

# Go from /scripts/common/ → /scripts/ → /Reddit_scraper/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

TEMP_CSV_FOLDER = os.path.join(BASE_DIR, "data_tmp")
os.makedirs(TEMP_CSV_FOLDER, exist_ok=True)

def clean_dataframe(df, text_column="Text"):
    """
    Clean a dataframe of Reddit posts.

    Operations:
    - remove rows where text is NaN
    - remove rows where text is empty/whitespace
    - remove duplicate texts
    - return cleaned df + removal stats
    """

    before = len(df)

    # Ensure the text column exists
    if text_column not in df.columns:
        raise KeyError(f"Column '{text_column}' not found in dataframe.")

    # Drop NaN
    df = df[df[text_column].notna()]

    # Remove empty/whitespace-only
    df = df[df[text_column].str.strip() != ""]

    after_text_filter = len(df)
    removed_empty = before - after_text_filter

    # Deduplicate by text
    before_dedupe = len(df)
    df = df.drop_duplicates(subset=[text_column])
    after_dedupe = len(df)
    removed_duplicate = before_dedupe - after_dedupe

    return df, removed_empty, removed_duplicate


def deduplicate_merged_csvs(csv_folder, quiet=False):
    """
    Deduplicate all *_merged.csv files in a folder.

    Operations per file:
    - drop duplicates by ID
    - drop duplicates by Text
    - overwrite the CSV in place

    Returns a list of dicts with filename, old_total, and new_total.
    """
    results = []

    for filename in os.listdir(csv_folder):
        if not filename.endswith("_merged.csv"):
            continue

        file_path = os.path.join(csv_folder, filename)
        df = pd.read_csv(file_path)

        old_total = len(df)
        df.drop_duplicates(subset=["ID"], inplace=True)
        df.drop_duplicates(subset=["Text"], inplace=True)
        new_total = len(df)

        df.to_csv(file_path, index=False)

        result = {
            "filename": filename,
            "old_total": old_total,
            "new_total": new_total,
        }
        results.append(result)

        if not quiet:
            print(f"Old total posts in {filename}: {old_total}")
            print(f"New total posts after deduplication in {filename}: {new_total}")

    return results
