# huntpacks/

Drop HuntPack `.html` files here, then run them:

```
python run_hunt.py -f huntpacks\YourPack.html
```

Or pull them straight from the online library (they download into this folder):

```
python run_hunt.py --list-remote            # browse all hunts, newest first
python run_hunt.py --latest 2               # pull & run the 2 newest
python run_hunt.py -f https://slapopotamus.github.io/HuntPack/hunts/<Pack>.html
```

This folder ships empty on purpose — no HuntPacks are bundled with the tool.
