import os
import time
import argparse
import sys
import shutil
import subprocess
from utils import load_json, save_json, scan_folder, norm_path
from crypto_utils import decrypt_file


def main():
    parser = argparse.ArgumentParser(description="Sync folder with other device. Pull method (decrypts incoming files).")
    parser.add_argument('-s', '--settings', required=True, help="path to settings JSON")
    args = parser.parse_args()

    settings = load_json(args.settings)
    pc_number = int(settings.get('pc_number'))
    folder_path = settings.get('folder_path')
    folder_metadata_path = settings.get('folder_metadata_path')
    updates_path = settings.get(f"folder_pc_{'1' if pc_number == 2 else '2'}_updates_path")
    files_to_sync_dir = settings.get(f"files_to_sync_from_pc_{'1' if pc_number == 2 else '2'}")
    git_cfg = settings.get('git', {})
    password = settings.get('encryption_password')

    if not all([pc_number, folder_path, folder_metadata_path, updates_path, files_to_sync_dir, git_cfg, password]):
        print("Error: settings.json missing required values.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(folder_path):
        print(f"Error: folder not found: {folder_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(folder_metadata_path):
        print(f"Error: metadata file not found: {folder_metadata_path}", file=sys.stderr)
        sys.exit(1)

    # pull latest from git
    repo_path = git_cfg.get('repo_path')
    remote = git_cfg.get('remote')
    branch = git_cfg.get('branch', 'main')
    token = git_cfg.get('token')

    if remote and token and repo_path:
        if remote.startswith('https://'):
            remote_with_token = remote.replace('https://', f'https://{token}@')
        else:
            remote_with_token = remote
        try:
            subprocess.run(['git', 'remote', 'set-url', 'origin', remote_with_token], cwd=repo_path, check=True)
            subprocess.run(['git', 'pull', 'origin', branch], cwd=repo_path, check=True)
            print(f"Pulled latest changes from {remote}/{branch}")
        except subprocess.CalledProcessError as e:
            print(f"Error during git pull: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Error: incomplete git config, skip pull.", file=sys.stderr)
        sys.exit(1)

    # load updates
    updates = load_json(updates_path)
    added = updates.get('added', [])
    deleted = updates.get('deleted', [])
    modified = updates.get('modified', [])

    if not (added or deleted or modified):
        print('No updates.')
        return

    # apply additions
    for rel in added:
        enc_src = norm_path(files_to_sync_dir, rel + '.enc')
        if not os.path.isfile(enc_src):
            print(f"Error: encrypted source not found for add -> {rel}", file=sys.stderr)
            continue

        # decrypt in place: writes rel (no .enc) next to enc_src
        dec_path = decrypt_file(enc_src, password)
        dst = norm_path(folder_path, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(dec_path, dst)
        print(f"Added -> {rel}")

    # apply deletions
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

    # apply modifications
    for rel in modified:
        enc_src = norm_path(files_to_sync_dir, rel + '.enc')
        if not os.path.isfile(enc_src):
            print(f"Warning: encrypted source missing for update -> {rel}", file=sys.stderr)
            continue

        dec_path = decrypt_file(enc_src, password)
        dst = norm_path(folder_path, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(dec_path, dst)
        print(f"Updated -> {rel}")

    # update metadata
    new_files_map = scan_folder(folder_path)
    new_meta = {"generated_at": time.time(), "files": new_files_map}
    save_json(folder_metadata_path, new_meta)

    # clear updates
    cleared = {"generated_at": time.time(), "added": [], "deleted": [], "modified": []}
    save_json(updates_path, cleared)

    # cleanup sync directory: remove both .enc files and any leftover decrypted files
    for rel in added + modified:
        enc_src = norm_path(files_to_sync_dir, rel + '.enc')
        if os.path.isfile(enc_src):
            os.remove(enc_src)
            print(f"Cleaned up encrypted -> {rel}.enc")
        dec_file = norm_path(files_to_sync_dir, rel)
        if os.path.isfile(dec_file):
            os.remove(dec_file)
            print(f"Cleaned up decrypted -> {rel}")
        # remove empty parent dirs
        parent = os.path.dirname(enc_src)
        try:
            os.removedirs(parent)
        except OSError:
            pass

    # git
    try:
        subprocess.run(["git", "add", updates_path, files_to_sync_dir], cwd=repo_path, check=True)
        commit_msg = f"PC{pc_number} folder-sync: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_path, check=True)
        subprocess.run(["git", "push", "origin", branch], cwd=repo_path, check=True)
        print(f"Pushed changes to {remote} ({branch})")
    except subprocess.CalledProcessError as e:
        print(f"Warning: git push failed: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
