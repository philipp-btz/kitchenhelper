import os
import json
from pathlib import Path


def list_menu_files(dir_path: str | None = None) -> list:
	"""Return a sorted list of file names in `dir_path`.

	If `dir_path` is None, the function uses the `menu_list` directory
	located next to this file. Works on Windows and Linux.
	"""
	if dir_path:
		base = Path(dir_path)
	else:
		base = Path(__file__).resolve().parent / "menu_list"

	try:
		base = base.resolve()
	except Exception:
		base = Path(dir_path) if dir_path else Path("menu_list")

	if not base.exists() or not base.is_dir():
		return []

	files = [p.name for p in sorted(base.iterdir()) if p.is_file()]
	return files

def push_menu(menu_data: dict, target_file: str = "config.json"):
    """Append `menu_data` to the JSON array in `target_file`.

    If `target_file` does not exist, it will be created with an array containing `menu_data`.
    """
    target_path = Path(target_file)
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    data.append(menu_data)

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(description="List files in the menu_list folder")
	parser.add_argument("--dir", "-d", help="Directory to list (default: repository's menu_list)")
	args = parser.parse_args()

	files = list_menu_files(args.dir)
	print(f"Found {len(files)} file(s): {files}")

	print("\n\n Bitte Gebe Die Nummer des Menüs ein, das du benutzen möchtest: \n\n")

	if not files:
		target = args.dir or (Path(__file__).resolve().parent / "menu_list")
		print(f"No files found in: {target}")
	else:
		for i in range(len(files)):
			print(f"({i+1}): {files[i]}")
		menu_nr = input("\n\n Nummer: \n\n")