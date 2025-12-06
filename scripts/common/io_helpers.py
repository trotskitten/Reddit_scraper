import os
import pandas as pd
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TEMP_CSV_FOLDER = os.path.join(BASE_DIR, "data_tmp")

os.makedirs(TEMP_CSV_FOLDER, exist_ok=True)

def merge_clean_save(
    df,
    merged_filename,
):
    """
    Simplified version:

    - If merged file exists, append new rows and dedupe by Text
    - If not, just use current df
    - Save back to merged file
    - Return simple stats:
        raw_total   = len(df) passed in
        old_total   = rows in existing merged file (0 if none)
        final_total = rows after merge + dedupe
        new_posts   = final_total - old_total
    """

    merged_path = os.path.join(TEMP_CSV_FOLDER, merged_filename)

    raw_total = len(df)

    if os.path.exists(merged_path):
        old_df = pd.read_csv(merged_path)
        combined = pd.concat([old_df, df], ignore_index=True)
    else:
        old_df = pd.DataFrame()
        combined = df.copy()

    old_total = len(old_df)

    combined.drop_duplicates(subset=["Text"], inplace=True)
    final_total = len(combined)

    new_posts = final_total - old_total

    combined.to_csv(merged_path, index=False)

    return {
        "raw_total": raw_total,
        "old_total": old_total,
        "final_total": final_total,
        "new_posts": new_posts,
    }
