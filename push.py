import os
import time
import argparse
import sys
import shutil
import subprocess
from utils import scan_folder, save_json, load_json, norm_path
from crypto_utils import encrypt_file


def compare_metadata(old_meta, new_meta):
    old_files = set(old_meta['files'])
    new_files = set(new_meta['files'])

    added   = new_files - old_files
    deleted = old_files - new_files

    # modified = files present in both but with different hashes
    modified = [
        f for f in (old_files & new_files)
        if old_meta['files'][f]['hash'] != new_meta['files'][f]['hash']
    ]

    # detect moved via hash matching
    moved = []
    if old_meta['files'] and 'hash' in next(iter(old_meta['files'].values())):
        old_by_hash = {}
        for f in deleted:
            h = old_meta['files'][f]['hash']
            old_by_hash.setdefault(h, []).append(f)

        new_by_hash = {}
        for f in added:
            h = new_meta['files'][f]['hash']
            new_by_hash.setdefault(h, []).append(f)

        for h, olds in old_by_hash.items():
            if h in new_by_hash:
                news = new_by_hash[h]
                for old_path, new_path in zip(sorted(olds), sorted(news)):
                    moved.append((old_path, new_path))
                    deleted.remove(old_path)
                    added.remove(new_path)

    # detect empty-dir deletions
    old_dirs = set(old_meta['dirs'])
    new_dirs = set(new_meta['dirs'])
    deleted_dirs = []
    for d in sorted(old_dirs - new_dirs):
        prefix = d + os.sep if d else ''
        if not any(f.startswith(prefix) for f in new_meta['files']):
            deleted_dirs.append(d or '.')

    return {
        "added":        sorted(added),
        "deleted":      sorted(deleted),
        "modified":     sorted(modified),
        "moved":        sorted(moved),
        "deleted_dirs": deleted_dirs
    }


def copy_and_encrypt_files(folder_path, files, dest_dir, public_key_path):
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
            continue

        encrypt_file(dst, public_key_path)
        os.remove(dst)


def main():
    parser = argparse.ArgumentParser(
        description="Scan a folder, record updates (incl. moves & empty-dir deletes), "
                    "stage content changes (encrypted), and push to git."
    )
    parser.add_argument('-s', '--settings', required=True, help="Path to settings JSON")
    args = parser.parse_args()

    # --- LOAD SETTINGS ---
    cfg = load_json(args.settings)
    pc_number        = int(cfg['pc_number'])
    folder_path      = cfg['folder_path']
    metadata_path    = cfg['folder_metadata_path']
    updates_path     = cfg[f'folder_pc_{pc_number}_updates_path']
    files_to_sync_dir= cfg[f'files_to_sync_from_pc_{pc_number}']
    git_cfg          = cfg['git']
    public_key_path  = cfg['public_key_path']

    # --- VALIDATE ---
    for p in (folder_path, metadata_path, updates_path, files_to_sync_dir, public_key_path):
        if not p:
            print("Error: settings.json missing a required key.", file=sys.stderr)
            sys.exit(1)
    if not os.path.isdir(folder_path):
        print(f"Error: folder not found: {folder_path}", file=sys.stderr); sys.exit(1)
    if not os.path.isfile(metadata_path):
        print(f"Error: metadata file not found: {metadata_path}", file=sys.stderr); sys.exit(1)


    # --- LOAD OLD META & SCAN NEW ---
    old_meta = load_json(metadata_path)
    scan = scan_folder(folder_path, old_meta=old_meta)
    new_meta = {
        'generated_at': time.time(),
        'files': scan['files'],
        'dirs':  scan['dirs'],
    }

    # --- DIFF ---
    diff = compare_metadata(old_meta, new_meta)
    added        = diff['added']
    deleted      = diff['deleted']
    modified     = diff['modified']
    moved        = [list(m) for m in diff['moved']]  # Convert tuples to lists
    deleted_dirs = diff['deleted_dirs']

    # --- MERGE INTO PENDING UPDATES JSON ---
    if os.path.isfile(updates_path):
        existing = load_json(updates_path)
    else:
        existing = {'added':[], 'deleted':[], 'modified':[], 'moved':[], 'deleted_dirs':[]}

    merged = {
        'generated_at': time.time(),
        'added':         sorted(set(existing.get('added',[])       + added)),
        'deleted':       sorted(set(existing.get('deleted',[])     + deleted)),
        'modified':      sorted(set(existing.get('modified',[])    + modified)),
        'moved':         sorted(set(tuple(x) for x in existing.get('moved',[])) | set(tuple(x) for x in moved)),
        'deleted_dirs':  sorted(set(existing.get('deleted_dirs',[])+ deleted_dirs)),
    }
    # convert moved back to list of lists for JSON compatibility
    merged['moved'] = [list(x) for x in merged['moved']]
    save_json(updates_path, merged)

    print(f"Updates recorded -> {updates_path}")
    print(f"  Added:           {len(added)}")
    print(f"  Deleted:         {len(deleted)}")
    print(f"  Modified:        {len(modified)}")
    print(f"  Moved:           {len(moved)}")
    print(f"  Empty-dirs del:  {len(deleted_dirs)}")

    # --- STAGE & ENCRYPT CONTENT CHANGES ---
    copy_and_encrypt_files(folder_path, added + modified, files_to_sync_dir, public_key_path)
    print(f"Staged & encrypted {len(added) + len(modified)} files -> {files_to_sync_dir}")

    # --- GIT PUSH ---
    if git_cfg and (added or deleted or modified or moved or deleted_dirs):
        repo_path = git_cfg.get('repo_path')
        remote    = git_cfg.get('remote')
        branch    = git_cfg.get('branch', 'main')
        token     = git_cfg.get('token')
        if not all([repo_path, remote, token]):
            print("Warning: incomplete git config, skipping push", file=sys.stderr)
        else:
            push_url = remote
            if remote.startswith('https://'):
                push_url = remote.replace('https://', f'https://{token}@')
            try:
                subprocess.run(
                    ['git','remote','set-url','origin',push_url],
                    cwd=repo_path, check=True
                )
                subprocess.run(
                    ['git','add', updates_path, files_to_sync_dir],
                    cwd=repo_path, check=True
                )
                msg = f"PC{pc_number} folder-sync: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                subprocess.run(['git','commit','-m',msg], cwd=repo_path, check=True)
                subprocess.run(['git','push','origin',branch], cwd=repo_path, check=True)
                print(f"Pushed changes to {remote} ({branch})")
            except subprocess.CalledProcessError as e:
                print(f"Warning: git push failed: {e}", file=sys.stderr)

    # --- SAVE NEW META ---
    new_meta['dirs'] = sorted(new_meta['dirs'])
    save_json(metadata_path, new_meta)
    print(f"Metadata updated -> {metadata_path}")


if __name__ == '__main__':
    main()
