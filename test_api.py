import requests

# Test against already running server
base_url = "http://localhost:8001"

# Test API key
api_key = "tsk_v7AcKSzC6Pe0caTyVuZk2FluUha_4CoBNDjRj1SHeZE"
api_headers = {'Authorization': f'Bearer {api_key}'}

# Test GET /sites with API key
response = requests.get(f"{base_url}/sites", headers=api_headers)
print('GET /sites with API key:', response.status_code, len(response.json()) if response.status_code == 200 else response.json())

# Test POST /sites with API key
site_data = {'siteCode': 'TEST-001', 'name': 'Test Site', 'siteType': 'Tower', 'location': 'Test Location', 'latitude': 5.0, 'longitude': -1.0, 'region': 'Test', 'laborCost': 1000}
response = requests.post(f"{base_url}/sites", json=site_data, headers=api_headers)
print('POST /sites with API key:', response.status_code, response.json())