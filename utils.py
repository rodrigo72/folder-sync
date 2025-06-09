import os
import json


def scan_folder(folder_path):
    meta = {}
    for root, _, files in os.walk(folder_path):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, folder_path)
            st = os.stat(full)
            meta[rel] = {
                "mtime": st.st_mtime,
                "size": st.st_size
            }
    return meta


def load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def norm_path(base, rel_path):
    parts = rel_path.replace('\\', '/').split('/')
    return os.path.join(base, *parts)
