import requests
import json

url = "http://localhost:8000/api/auth/register/"

# Minimal test data
data = {
    "username": "testuser123",
    "email": "test@example.com", 
    "password": "testpass123",
    "confirm_password": "testpass123",
    "first_name": "Test",
    "last_name": "User",
    "id_number": "87654321",
    "phone_no": "0798765432"
}

print(f"Sending request to: {url}")
print(f"Data: {json.dumps(data, indent=2)}")

try:
    response = requests.post(url, json=data)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")