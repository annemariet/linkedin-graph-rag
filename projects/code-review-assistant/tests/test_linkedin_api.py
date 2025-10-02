import os
import requests
from dotenv import load_dotenv
from linkedin_api.clients.restli.client import RestliClient

# Load environment variables from .env file
load_dotenv()

# Get access token from environment variable
access_token = os.getenv('LINKEDIN_ACCESS_TOKEN')
if not access_token:
    print("Error: LINKEDIN_ACCESS_TOKEN environment variable not set in .env file")
    exit(1)

# LinkedIn API base URL
base_url = "https://api.linkedin.com/rest"

# Headers for authentication
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
    "LinkedIn-Version": "202312"
}

try:
    print("\nTesting /memberAuthorizations...")
    response = requests.get(
        f"{base_url}/memberAuthorizations",
        headers=headers,
        params = {
            "q": "memberAndApplication"
        }
    )
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Response:", response.json())
    else:
        print("Error Response:", response.text)
except Exception as e:
    print(f"Error: {e}")

try:
    print("\nTesting /memberChangeLogs...")
    response = requests.get(
        f"{base_url}/memberChangeLogs",
        headers=headers,
        params = {
            "q": "memberAndApplication"
        }
    )
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Response:", response.json())
    else:
        print("Error Response:", response.text)
except Exception as e:
    print(f"Error: {e}")
