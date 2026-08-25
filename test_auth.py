import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Test against already running server
base_url = "http://localhost:8001"

# Test login
response = requests.post(f"{base_url}/auth/login", json={'username': 'admin', 'password': 'admin123'})
print('Login:', response.status_code, response.json())
token = response.json()['access_token']

headers = {'Authorization': f'Bearer {token}'}

# Test protected endpoint with token
response = requests.get(f"{base_url}/sites", headers=headers)
print('Sites:', response.status_code, len(response.json()) if response.status_code == 200 else response.json())

# Test wrong password
response = requests.post(f"{base_url}/auth/login", json={'username': 'admin', 'password': 'wrong'})
print('Wrong password:', response.status_code, response.json())

# Test manager login
response = requests.post(f"{base_url}/auth/login", json={'username': 'manager', 'password': 'manager123'})
print('Manager login:', response.status_code, response.json())

# Test API key
api_key = os.environ.get('VALID_API_KEYS', '').split(',')[0]
api_headers = {'Authorization': f'Bearer {api_key}'}
response = requests.get(f"{base_url}/sites", headers=api_headers)
print('API key:', response.status_code, len(response.json()) if response.status_code == 200 else response.json())

# Test protected write endpoint
site_data = {'siteCode': 'TEST-001', 'name': 'Test Site', 'siteType': 'Tower', 'location': 'Test Location', 'latitude': 5.0, 'longitude': -1.0, 'region': 'Test', 'laborCost': 1000}
response = requests.post(f"{base_url}/sites", json=site_data, headers=api_headers)
print('Create site via API key:', response.status_code, response.json())

# Test without auth
response = requests.post(f"{base_url}/sites", json={'siteCode': 'TEST-002', 'name': 'Test Site', 'siteType': 'Tower', 'location': 'Test Location', 'latitude': 5.0, 'longitude': -1.0, 'region': 'Test', 'laborCost': 1000})
print('No auth:', response.status_code, response.json())

print('\nAll tests passed!')


