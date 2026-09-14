#!/usr/bin/env python3
import json
import urllib.request
import subprocess
import sys
import os
import time

def main():
    print("Fetching 100 real Norwegian organizations for the benchmark...")
    try:
        url = "https://data.brreg.no/enhetsregisteret/api/enheter?size=100"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))
        orgs = data.get("_embedded", {}).get("enheter", [])
        if not orgs:
            print("Failed to fetch organizations from Brreg.")
            sys.exit(1)
            
        with open("benchmark-companies.jsonl", "w", encoding="utf-8") as f:
            for org in orgs:
                f.write(json.dumps({"organisation_number": org["organisasjonsnummer"]}) + "\n")
        print(f"Saved {len(orgs)} organizations to benchmark-companies.jsonl")
    except Exception as e:
        print("Error fetching orgs:", e)
        sys.exit(1)

    print("\n--- Clearing stale DB and outputs ---")
    def safe_remove(path):
        try:
            os.remove(path)
            print(f"  Removed {path}")
        except FileNotFoundError:
            pass
        except PermissionError:
            print(f"  WARNING: Could not remove {path} (locked). Run may use stale data.")

    for stale in ["db/signalpost.db", "out/benchmark-envelopes.jsonl", "out/benchmark-profiles.jsonl", "out/benchmark-report.json"]:
        safe_remove(stale)

    print("\n--- Starting Orchestrator Run ---")
    start_time = time.time()
    
    cmd = [
        sys.executable, "-u", "scripts/run_competition_batch.py",
        "--organisations", "benchmark-companies.jsonl",
        "--bulk", "brreg-enheter.csv",
        "--profiles-output", "out/benchmark-profiles.jsonl",
        "--output", "out/benchmark-envelopes.jsonl",
        "--report", "out/benchmark-report.json",
        "--run-id", "benchmark-001",
        "--expected-count", "100"
    ]
    
    # We use subprocess.call and stream output
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        print(line, end="")
        sys.stdout.flush()
    proc.wait()
    
    wall_clock_time = time.time() - start_time
    print(f"\n--- Run Completed in {wall_clock_time/60:.2f} minutes ---")
    
    if proc.returncode != 0:
        print(f"ERROR: Process exited with non-zero code {proc.returncode}")
        sys.exit(1)
        
    print("\n--- Validating Results ---")
    
    # Load report
    if not os.path.exists("out/benchmark-report.json"):
        print("ERROR: Report file out/benchmark-report.json not found.")
        sys.exit(1)
        
    with open("out/benchmark-report.json", "r") as f:
        report = json.load(f)
        
    requests = report.get("operations", {}).get("requests", 0)
    print(f"Total Outbound Requests: {requests}")
    if requests >= 2000:
        print("ERROR: Too many requests!")
        sys.exit(1)
        
    # OpenRouter Cost Estimation (Assuming ~$0.001 per profile if we did simple extractions)
    cost = 0.001 * len(orgs)  # Placeholder simple logic since cost is in envelopes
    
    # Load envelopes
    if not os.path.exists("out/benchmark-envelopes.jsonl"):
        print("ERROR: Envelope file out/benchmark-envelopes.jsonl not found.")
        sys.exit(1)
        
    envelopes = []
    with open("out/benchmark-envelopes.jsonl", "r") as f:
        for line in f:
            envelopes.append(json.loads(line.strip()))
            
    print(f"Total Envelopes: {len(envelopes)}")
    if len(envelopes) != 100:
        print("ERROR: Did not emit exactly 100 envelopes.")
        sys.exit(1)
        
    valid_availabilities = {"available", "not_available", "blocked", "not_applicable", "ambiguous", "failed"}
    
    total_cost = 0.0
    for env in envelopes:
        total_cost += env.get("operations", {}).get("third_party_cost_usd", 0.0)
        
        claims = env.get("claims", [])
        evidence_dict = {ev["id"]: ev for ev in env.get("evidence", [])}
        
        for claim in claims:
            # 1. Check valid status/availability
            avail = claim.get("availability")
            if avail not in valid_availabilities:
                print(f"ERROR: Invalid availability status '{avail}' in org {env['organisation_number']}")
                sys.exit(1)
                
            # 2. Check falsified zeros
            field = claim.get("field")
            val = claim.get("value")
            if field in ["revenue", "profit", "employees"] and val == "0":
                print(f"ERROR: Falsified zero detected in field '{field}' for org {env['organisation_number']}")
                sys.exit(1)
                
            # 3. Evidence provenance
            evidence_ids = claim.get("evidence_ids", [])
            for eid in evidence_ids:
                ev = evidence_dict.get(eid)
                if not ev:
                    print(f"ERROR: Missing evidence {eid} for org {env['organisation_number']}")
                    sys.exit(1)
                if not ev.get("source_url"):
                    print(f"ERROR: Missing source_url in evidence {eid}")
                    sys.exit(1)
                if not ev.get("retrieved_at"):
                    print(f"ERROR: Missing retrieved_at in evidence {eid}")
                    sys.exit(1)
                    
    print(f"Total OpenRouter Estimated Cost: ${total_cost:.4f}")
    if total_cost >= 10.0:
        print("ERROR: Total cost exceeds $10 cap!")
        sys.exit(1)
        
    if wall_clock_time > 45 * 60:
        print("ERROR: Wall clock time exceeded 45 minutes limit!")
        sys.exit(1)

    print("\nSUCCESS: All benchmark criteria and validations passed cleanly!")
    sys.exit(0)

if __name__ == "__main__":
    main()
