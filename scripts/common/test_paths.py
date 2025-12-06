import os

# Simulate the same logic used in cleaning.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TEMP_CSV_FOLDER = os.path.join(BASE_DIR, "data_tmp")

# Create folder if missing
os.makedirs(TEMP_CSV_FOLDER, exist_ok=True)

print("Current file:", __file__)
print("Detected BASE_DIR:", BASE_DIR)
print("Temp folder path:", TEMP_CSV_FOLDER)

# Test writing a CSV
import pandas as pd

df = pd.DataFrame({"Test": ["hello", "world"]})
test_path = os.path.join(TEMP_CSV_FOLDER, "test_output.csv")
