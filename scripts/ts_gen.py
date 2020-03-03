# https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html
import json
import os
import time

from scripts.util.ts_structures import Declaration

import requests
import requests_cache
requests_cache.install_cache(allowable_codes=(200, 404))


def dl(url: str, file_name: str):
    req = requests.get(url)

    try:
        with open('../ts/' + file_name, 'wb') as f:
            f.write(req.content)
    except ValueError:
        print("Cannot access " + url)


if __name__ == "__main__":
    print("This script will generate your typescript declarations, hang tight...")
    decl = Declaration()
    for root, dirs, files in os.walk("../api/"):
        for file in files:
            if '.json' in file and 'api-index' not in file:
                lib_name = file[:len('.json')*-1]
                with open(os.path.join(root, file), encoding="utf8") as f:
                    decl.load(json.load(f), lib_name)
    print("Done loading!")
    print("Now cleaning up... ", end="", flush=True)
    decl.clean_up()
    print("Done!")
    print("Now writing...", end="", flush=True)
    decl.save_to("../ts/")
    print("Done!")
    print("Getting additional types...", end="", flush=True)
    dl("https://raw.githubusercontent.com/DefinitelyTyped/DefinitelyTyped/master/types/jquery/v2/index.d.ts", "external.jQuery.d.ts")
    print("Done!")
    print("\nAll done!")
    time.sleep(2)
