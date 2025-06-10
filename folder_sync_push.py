import os
import time
import argparse
import sys
import shutil
import subprocess
from utils import scan_folder, save_json, load_json, norm_path


def compare_metadata(old_meta, new_meta):
    old_files = set(old_meta.get('files', {}))
    new_files = set(new_meta.get('files', {}))

    added = sorted(new_files - old_files)
    deleted = sorted(old_files - new_files)
    modified = []
    for f in sorted(old_files & new_files):
        o = old_meta['files'][f]
        n = new_meta['files'][f]
        if o['mtime'] != n['mtime'] or o['size'] != n['size']:
            modified.append(f)
    return added, deleted, modified


def copy_files(folder_path, files, dest_dir):
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)

    for rel in files:
        src = norm_path(folder_path, rel)
        dst = norm_path(dest_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.copy2(src, dst)
        except FileNotFoundError:
            print(f"Warning: source not found for copy -> {rel}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Scan a folder, record updates, stage files to sync, and push to git.")
    parser.add_argument('-s', '--settings', required=True, help="Path to settings JSON")
    args = parser.parse_args()

    settings = load_json(args.settings)
    pc_number = int(settings.get('pc_number'))
    folder_path = settings.get('folder_path')
    folder_metadata_path = settings.get('folder_metadata_path')
    updates_path = settings.get(f'folder_pc_{'1' if pc_number == 1 else '2'}_updates_path')
    files_to_sync_dir = settings.get(f'files_to_sync_from_pc_{'1' if pc_number == 1 else '2'}')
    git_cfg = settings.get('git', {})

    if not all([folder_path, folder_metadata_path, updates_path, files_to_sync_dir, git_cfg]):
        print("Error: settings.json missing required keys.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(folder_path):
        print(f"Error: folder not found: {folder_path}", file=sys.stderr)
        sys.exit(1)

    # initialize metadata
    if not os.path.isfile(folder_metadata_path):
        print(f"Error: metadata file not found: {folder_metadata_path}", file=sys.stderr)
        sys.exit(1)

    # load existing metadata and scan folder
    old_meta = load_json(folder_metadata_path)
    new_map = scan_folder(folder_path)
    new_meta = {'generated_at': time.time(), 'files': new_map}

    # compare
    added, deleted, modified = compare_metadata(old_meta, new_meta)

    # merge with existing updates
    existing = load_json(updates_path) if os.path.isfile(updates_path) else {'added': [], 'deleted': [], 'modified': []}
    merged = {
        'generated_at': time.time(),
        'added': sorted(set(existing['added'] + added)),
        'deleted': sorted(set(existing['deleted'] + deleted)),
        'modified': sorted(set(existing['modified'] + modified))
    }
    save_json(updates_path, merged)

    print(f"Updates recorded -> {updates_path}")
    print(f"  Added:   {len(added)}")
    print(f"  Deleted: {len(deleted)}")
    print(f"  Modified:{len(modified)}")

    # stage added & modified files
    copy_files(folder_path, added + modified, files_to_sync_dir)
    print(f"Staged {len(added) + len(modified)} files -> {files_to_sync_dir}")

    # git push 
    if git_cfg and (added or deleted or modified):
        repo_path = git_cfg.get('repo_path')
        remote = git_cfg.get('remote')
        branch = git_cfg.get('branch', 'main')
        token = git_cfg.get('token')
        if not all([repo_path, remote, token]):
            print("Warning: incomplete git config, skipping push", file=sys.stderr)
        else:
            url = remote
            if remote.startswith('https://'):
                url = remote.replace('https://', f'https://{token}@')
            try:
                subprocess.run(['git', 'remote', 'set-url', 'origin', url], cwd=repo_path, check=True)
                subprocess.run(['git', 'add', updates_path, files_to_sync_dir], cwd=repo_path, check=True)
                msg = f"PC{pc_number} folder-sync: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                subprocess.run(['git', 'commit', '-m', msg], cwd=repo_path, check=True)
                subprocess.run(['git', 'push', 'origin', branch], cwd=repo_path, check=True)
                print(f"Pushed changes to {remote} ({branch})")
            except subprocess.CalledProcessError as e:
                print(f"Warning: git push failed: {e}", file=sys.stderr)

    # save new metadata
    save_json(folder_metadata_path, new_meta)
    print(f"Metadata updated -> {folder_metadata_path}")


if __name__ == '__main__':
    main()
