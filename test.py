from pathlib import Path
import os
import json
'''
output_file = Path("some/path/file.txt")
output_file.parent.mkdir(exist_ok=True, parents=True)
output_file.write_text("some text")
'''
defaults = {}
if os.path.isfile(".local/user_settings/user_settings.json"):
    with open(".local/user_settings/user_settings.json", "r", encoding="utf-8") as f:
        settings_dict = json.load(f)
        defaults.update(settings_dict)
        for key, value in settings_dict.items():
            os.environ[key] = value
            print("addasd")
print("ok")