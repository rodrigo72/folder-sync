import os
import time
import argparse
import sys
from utils import scan_folder, save_json, load_json
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Init metadata (before any first push or pull)")
    parser.add_argument('-s', '--settings', required=True, help="Path to settings JSON")
    args = parser.parse_args()

    settings = load_json(args.settings)
    pc_number = int(settings.get('pc_number'))
    folder_path = settings.get('folder_path')
    folder_metadata_path = settings.get('folder_metadata_path')

    if not all([folder_path, folder_metadata_path]):
        print("Error: settings.json missing required keys.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(folder_path):
        print(f"Error: folder not found: {folder_path}", file=sys.stderr)
        sys.exit(1)

    # making sure these files and directories exist
    folder_pc_1_updates_path = settings.get('folder_pc_1_updates_path')
    folder_pc_2_updates_path = settings.get('folder_pc_2_updates_path')
    files_to_sync_from_pc_1 = settings.get('files_to_sync_from_pc_1')
    files_to_sync_from_pc_2 = settings.get('files_to_sync_from_pc_2')

    if not all([folder_pc_1_updates_path, folder_pc_2_updates_path, 
                files_to_sync_from_pc_1, files_to_sync_from_pc_2]):
        print("Error: settings.json missing required keys.", file=sys.stderr)
        print("Could not create necessary directories.")
    else:
        os.makedirs(files_to_sync_from_pc_1, exist_ok=True)  # dir
        os.makedirs(files_to_sync_from_pc_2, exist_ok=True)  # dir

        folder_pc_1_updates_path = Path(folder_pc_1_updates_path)
        if not folder_pc_1_updates_path.exists():
            folder_pc_1_updates_path.parent.mkdir(parents=True, exist_ok=True)
            with open(folder_pc_1_updates_path, 'w') as f:
                json.dump({}, f)

        folder_pc_2_updates_path = Path(folder_pc_2_updates_path)
        if not folder_pc_2_updates_path.exists():
            folder_pc_2_updates_path.parent.mkdir(parents=True, exist_ok=True)
            with open(folder_pc_2_updates_path, 'w') as f:
                json.dump({}, f)

    # initialize metadata
    if not os.path.isfile(folder_metadata_path):
        scan_data = scan_folder(folder_path, old_meta=None)
        metadata = {
            'generated_at': time.time(),
            'files': scan_data['files'],
            'dirs':  sorted(scan_data['dirs']),  # from set to list -> serializable
        }
        save_json(folder_metadata_path, metadata)
        print(f"Initialized metadata -> {folder_metadata_path}")
        return
    else:
        print("Metadata file already exists.")


if __name__ == '__main__':
    main()
