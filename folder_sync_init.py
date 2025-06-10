
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

    # initialize metadata
    if not os.path.isfile(folder_metadata_path):
        new_files = scan_folder(folder_path)
        metadata = {'generated_at': time.time(), 'files': new_files}
        save_json(folder_metadata_path, metadata)
        print(f"Initialized metadata ({len(new_files)} files) -> {folder_metadata_path}")
        return
    else:
        print("Metadata file already exists.")


if __name__ == '__main__':
    main()
