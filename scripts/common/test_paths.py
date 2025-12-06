import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TEMP_CSV_FOLDER = os.path.join(BASE_DIR, "data_tmp")

os.makedirs(TEMP_CSV_FOLDER, exist_ok=True)

print("Current file:", __file__)
print("Detected BASE_DIR:", BASE_DIR)
print("Temp folder path:", TEMP_CSV_FOLDER)

df = pd.DataFrame({"Test": ["hello", "world"]})
test_path = os.path.join(TEMP_CSV_FOLDER, "test_output.csv")

print("Attempting to write CSV at:", test_path)

df.to_csv(test_path, index=False)

print("Exists?", os.path.exists(test_path))
