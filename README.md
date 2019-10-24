# UI5 API in your IDE!

This projects queries the official UI5 API and creates TypeScript declarations based on that, so that you IDE can support you writing UI5 JS code.

### SetUp:
 - clone this repository somewhere to your machine (e.g. `C:\PortableIDE\ui5ApiTs`)
 - make sure to have python3 installed (you can download it [here](https://www.python.org/ftp/python/3.8.0/python-3.8.0-amd64.exe))
 - open up a command prompt and run `pip install requests requests_cache bs4`
 - go to the `scripts` folder of this repository
 - execute `download.py` (double-click the file)
 - execute `ts_gen.py`
 - Now you have up-to-date ui5 type declarations!
 
### Embedding it into WebStorm
 - open up `Settings > Languages & Frameworks > JavaScript > Libraries`
 - click on `Add...`
 - give it a nice name (like "`My personal UI5`")
 - set the visibility to global
 - click on the small "`+`" on the side and choose `Attach Directories...`
 - navigate to the `ts` folder of this repository
 - That's it!
 - In other projects (when switching between frontends), you might need to open up the settings again, navigate to this library and give it the `enabled` tick