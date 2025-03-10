import json
import os

def save_report(report_data, file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(report_data, f, indent=2)

def load_report(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)