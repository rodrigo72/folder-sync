import os
import time
import argparse
import sys
import shutil
import subprocess

from utils import load_json, save_json, scan_folder, norm_path
from crypto_utils import decrypt_file


def main():
    parser = argparse.ArgumentParser(
        description="Sync folder with other device. Pull method (decrypts incoming files)."
    )
    parser.add_argument('-s', '--settings', required=True, help="path to settings JSON")
    args = parser.parse_args()

    # ------- LOAD SETTINGS -------
    settings = load_json(args.settings)
    pc_number            = int(settings.get('pc_number'))
    folder_path          = settings.get('folder_path')
    metadata_path        = settings.get('folder_metadata_path')
    updates_path         = settings.get(f"folder_pc_{'1' if pc_number == 2 else '2'}_updates_path")
    sync_dir             = settings.get(f"files_to_sync_from_pc_{'1' if pc_number == 2 else '2'}")
    git_cfg              = settings.get('git', {})
    private_key_path     = settings.get('private_key_path')

    # ------- VALIDATE -------
    if not all([folder_path, metadata_path, updates_path, sync_dir, private_key_path]):
        print("Error: settings.json missing required values.", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(folder_path):
        print(f"Error: folder not found: {folder_path}", file=sys.stderr); sys.exit(1)
    if not os.path.isfile(metadata_path):
        print(f"Error: metadata file not found: {metadata_path}", file=sys.stderr); sys.exit(1)

    # ------- GIT PULL -------
    repo_path = git_cfg.get('repo_path')
    remote    = git_cfg.get('remote')
    branch    = git_cfg.get('branch', 'main')
    token     = git_cfg.get('token')

    if repo_path and remote and token:
        pull_url = remote
        if remote.startswith('https://'):
            pull_url = remote.replace('https://', f'https://{token}@')
        try:
            subprocess.run(['git','remote','set-url','origin',pull_url], cwd=repo_path, check=True)
            subprocess.run(['git','pull','origin',branch], cwd=repo_path, check=True)
            print(f"Pulled latest changes from {remote}/{branch}")
        except subprocess.CalledProcessError as e:
            print(f"Error during git pull: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Error: incomplete git config, skip pull.", file=sys.stderr)
        sys.exit(1)

    # ------- LOAD UPDATES -------
    updates = load_json(updates_path) or {}
    added        = updates.get('added', [])
    deleted      = updates.get('deleted', [])
    modified     = updates.get('modified', [])
    moved        = updates.get('moved', [])          # list of [old_rel, new_rel]
    deleted_dirs = updates.get('deleted_dirs', [])

    if not (added or deleted or modified or moved or deleted_dirs):
        print("No updates.")
        return

    # ------- APPLY FILE DELETIONS -------
    for rel in deleted:
        tgt = norm_path(folder_path, rel)
        if os.path.isdir(tgt):
            shutil.rmtree(tgt)
            print(f"Deleted directory -> {rel}")
        elif os.path.isfile(tgt):
            os.remove(tgt)
            print(f"Deleted file -> {rel}")
        else:
            print(f"Warning: target not found for delete -> {rel}", file=sys.stderr)

    # ------- APPLY MOVES -------
    for old_rel, new_rel in moved:
        src = norm_path(folder_path, old_rel)
        dst = norm_path(folder_path, new_rel)
        if not os.path.exists(src):
            print(f"Warning: source not found for move -> {old_rel}", file=sys.stderr)
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        print(f"Moved -> {old_rel} → {new_rel}")

    # ------- APPLY EMPTY-DIR DELETIONS -------
    for rel in deleted_dirs:
        dir_path = norm_path(folder_path, rel)
        try:
            os.removedirs(dir_path)
            print(f"Deleted empty directory -> {rel}")
        except OSError:
            # either not empty or doesn't exist
            pass

    # ------- APPLY ADDITIONS -------
    for rel in added:
        enc_src = norm_path(sync_dir, rel + '.enc')
        if not os.path.isfile(enc_src):
            print(f"Error: encrypted source not found for add -> {rel}", file=sys.stderr)
            continue

        dec_path = decrypt_file(enc_src, private_key_path)
        dst = norm_path(folder_path, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(dec_path, dst)
        print(f"Added -> {rel}")

    # ------- APPLY MODIFICATIONS -------
    for rel in modified:
        enc_src = norm_path(sync_dir, rel + '.enc')
        if not os.path.isfile(enc_src):
            print(f"Warning: encrypted source missing for update -> {rel}", file=sys.stderr)
            continue

        dec_path = decrypt_file(enc_src, private_key_path)
        dst = norm_path(folder_path, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(dec_path, dst)
        print(f"Updated -> {rel}")

    # ------- REFRESH METADATA -------
    old_meta = load_json(metadata_path)
    scan = scan_folder(folder_path, old_meta=old_meta)
    new_meta = {
        'generated_at': time.time(),
        'files': scan['files'],
        'dirs':  sorted(scan['dirs'])
    }
    save_json(metadata_path, new_meta)

    # ------- CLEAR UPDATES -------
    cleared = {
        'generated_at': time.time(),
        'added':        [],
        'deleted':      [],
        'modified':     [],
        'moved':        [],
        'deleted_dirs': []
    }
    save_json(updates_path, cleared)

    # ------- CLEAN SYNC FOLDER -------
    # remove any leftover .enc and decrypted files
    for rel in added + modified:
        enc = norm_path(sync_dir, rel + '.enc')
        if os.path.isfile(enc):
            os.remove(enc)
        dec = norm_path(sync_dir, rel)
        if os.path.isfile(dec):
            os.remove(dec)
        # try to remove empty parent dirs
        parent = os.path.dirname(enc)
        try:
            os.removedirs(parent)
        except OSError:
            pass

    # ------- GIT COMMIT & PUSH -------
    try:
        subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
        msg = f"PC{pc_number} folder-sync: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git','commit','-m', msg], cwd=repo_path, check=True)
        subprocess.run(['git','push','origin', branch], cwd=repo_path, check=True)
        print(f"Pushed changes to {remote} ({branch})")
    except subprocess.CalledProcessError as e:
        print(f"Warning: git push failed: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
