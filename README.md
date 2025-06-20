# folder-sync

A lightweight, git-backed bi-directional folder sync that uses metadata diffs and per-file public-key encryption, storing only encrypted unsynced data and json files (with the update instructions) in the repo.
Note: The folders on their respective devices must be initialized with the same data (init.py).
