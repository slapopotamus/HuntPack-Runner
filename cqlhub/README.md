# cqlhub/

CQL-Hub YAML queries downloaded from
[ByteRay-Labs/Query-Hub](https://github.com/ByteRay-Labs/Query-Hub) land here.

```
python run_hunt.py --source cqlhub --list-remote     # browse the ~150 detections
python run_hunt.py --source cqlhub --pick 5-10        # pull & run by number
python run_hunt.py -f https://raw.githubusercontent.com/ByteRay-Labs/Query-Hub/main/queries/<Name>.yml
python run_hunt.py -f cqlhub\<Name>.yml               # run a local one
```

Each `.yml` file is one detection. Some queries correlate against **lookup
files** (Tor exit nodes, cloud IP ranges, LOLBAS, etc.) that must be uploaded to
your NG-SIEM first — those are flagged with a `// NOTE: references a lookup file`
line and will error until the lookup exists in your tenant.

This folder ships empty on purpose.
