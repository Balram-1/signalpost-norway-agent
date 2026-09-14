import json, urllib.request

d = json.loads(urllib.request.urlopen('https://data.brreg.no/enhetsregisteret/api/enheter?size=7').read())
orgs = ['925380431', '984851146', '984851006'] + [e['organisasjonsnummer'] for e in d['_embedded']['enheter']]

with open('smoke-companies.jsonl', 'w') as f:
    for o in orgs:
        f.write(json.dumps({"organisation_number": o}) + "\n")
print(f"Created smoke-companies.jsonl with {len(orgs)} companies")
