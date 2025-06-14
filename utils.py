import os
import json
import hashlib


def scan_folder(folder_path, compute_hash=True, old_meta=None):
    meta = {'files': {}, 'dirs': set()}

    for root, dirs, files in os.walk(folder_path):
        rel_dir = os.path.relpath(root, folder_path)
        if rel_dir == '.':
            rel_dir = ''
        meta['dirs'].add(rel_dir)

        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.join(rel_dir, fn) if rel_dir else fn
            st = os.stat(full)
            entry = {
                "mtime": st.st_mtime,
                "ctime": st.st_ctime,
                "size":  st.st_size
            }

            if compute_hash:
                reuse = False
                if old_meta:
                    old = old_meta.get('files', {}).get(rel)
                    if old:
                        if (old['mtime'] == entry['mtime']
                            and old['ctime'] == entry['ctime']
                            and old['size']  == entry['size']):
                            entry['hash'] = old['hash']
                            reuse = True

                if not reuse:
                    entry['hash'] = _hash_file(full)

            meta['files'][rel] = entry

    return meta


def _hash_file(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}")


def save_json(path, data):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    temp_path = path + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(temp_path, path)



def norm_path(base, rel_path):
    parts = rel_path.replace('\\', '/').split('/')
    return os.path.join(base, *parts)
