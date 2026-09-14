import json
import urllib.request
import os

def fetch_json(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

def get_companies():
    # 1. Defunct company
    print("Finding defunct company...")
    defunct_data = fetch_json('https://data.brreg.no/enhetsregisteret/api/enheter?slettedato=fra:2020-01-01&size=1')
    defunct_org = defunct_data['_embedded']['enheter'][0]['organisasjonsnummer']
    
    # 2. Underenhet with parent
    print("Finding underenhet...")
    under_data = fetch_json('https://data.brreg.no/enhetsregisteret/api/underenheter?size=1')
    under_org = under_data['_embedded']['underenheter'][0]['organisasjonsnummer']
    
    # 3. 7 regular companies
    print("Finding regular companies...")
    reg_data = fetch_json('https://data.brreg.no/enhetsregisteret/api/enheter?size=7')
    reg_orgs = [e['organisasjonsnummer'] for e in reg_data['_embedded']['enheter']]
    
    # 4. Big company (DNB Bank ASA)
    dnb_org = "984851006"
    
    orgs = [defunct_org, under_org, dnb_org] + reg_orgs
    
    # Write to smoke-companies.jsonl
    with open('smoke-companies.jsonl', 'w') as f:
        for org in orgs:
            f.write(json.dumps({"organisation_number": org}) + "\n")
            
    print(f"Generated smoke-companies.jsonl with {len(orgs)} organizations: {orgs}")

if __name__ == "__main__":
    get_companies()
    
    if not os.path.exists("brreg-enheter.csv"):
        print("Please download brreg-enheter.csv using curl")
