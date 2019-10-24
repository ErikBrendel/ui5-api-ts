import requests
import requests_cache
import time

requests_cache.install_cache()

BASE_API_URL = "https://sapui5.hana.ondemand.com/docs/api/api-index.json"
URL_START = "https://sapui5.hana.ondemand.com/test-resources/"
URL_END = "/designtime/apiref/api.json"


def url_for_module(name: str) -> str:
    return URL_START + name.replace(".", "/") + URL_END


def dl(url: str, file_name: str) -> dict:
    req = requests.get(url)

    # 2. Handle error if deserialization fails (because of no text or bad format)
    try:
        result_json = req.json()
        with open('../api/' + file_name + '.json', 'wb') as f:
            f.write(req.content)
        print("Sccuess! " + url)
        return result_json
    except ValueError:
        print("Cannot access " + url)
        return {}


def load_main_node(symbol: dict):
    name = symbol['name']
    dl(url_for_module(name), name)
    if "nodes" in symbol:
        for sub_node in symbol["nodes"]:
            load_main_node(sub_node)


def load_entrypoint():
    json_result = dl(BASE_API_URL, "api-index")

    for symbol in json_result["symbols"]:
        load_main_node(symbol)


if __name__ == "__main__":
    print("This script will download the latest UI5 API information, hang tight...")
    load_entrypoint()
    print("\nAll done!")
    time.sleep(2)
