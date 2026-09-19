"""Submit synthetic examples to the running local desk. Safe to replay exact inputs."""
import argparse
import json
from pathlib import Path
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8765')
parser.add_argument('--scenario', choices=('quickstart', 'review-ordering'), default='quickstart')
args = parser.parse_args()
with urllib.request.urlopen(args.url + '/api/dashboard', timeout=5) as response:
    if json.load(response)['mode'] != 'local':
        raise SystemExit('Demo seeding is restricted to local CRM mode.')
filename = 'review-ordering.json' if args.scenario == 'review-ordering' else 'demo-leads.json'
for lead in json.loads((Path(__file__).parent/'examples'/filename).read_text()):
    req = urllib.request.Request(args.url+'/api/leads', json.dumps(lead).encode(), {'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.load(response)
    print(f"{lead['event_id']}: {result['event']['status']} | duplicate={result['duplicate']}")
