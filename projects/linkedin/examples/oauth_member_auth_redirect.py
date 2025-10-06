"""
This example illustrates a basic example of the oauth authorization code flow.

Pre-requisites:
1. Add CLIENT_ID, CLIENT_SECRET, and OAUTH2_REDIRECT_URL variables to the top-level .env file.
The OAUTH2_REDIRECT_URL should be set to "http://localhost:3000/oauth".
2. The associated developer app you are using should have access to r_liteprofile, which can be
obtained through requesting the self-serve Sign In With LinkedIn API product on the LinkedIn
Developer Portal.
3. Set your developer app's OAuth redirect URL to "http://localhost:3000/oauth" from the Developer Portal

Steps:
1. Run script: `python3 oauth-member-auth-redirect.py`
2. Navigate to localhost:3000
3. Login as LinkedIn member and authorize application
4. View member profile data
"""
import os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, redirect, request
from dotenv import load_dotenv, find_dotenv
from linkedin_api.clients.auth.client import AuthClient
import requests

load_dotenv(find_dotenv())

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
OAUTH2_REDIRECT_URL = os.getenv("LINKEDIN_OAUTH2_REDIRECT_URL")

# Debug logging
print(f"CLIENT_ID: {CLIENT_ID}")
print(f"CLIENT_SECRET: {'***' if CLIENT_SECRET else 'None'}")
print(f"OAUTH2_REDIRECT_URL: {OAUTH2_REDIRECT_URL}")

app = Flask(__name__)

access_token = None

auth_client = AuthClient(
    client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_url=OAUTH2_REDIRECT_URL
)


@app.route("/", methods=["GET"])
def main():
    global access_token
    if access_token == None:
        return redirect(auth_client.generate_member_auth_url(scopes=["r_dma_portability_self_serve"]))
    else:
        try:
            # Use direct HTTP requests for Member Data Portability API
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Try memberSnapshotData endpoint
            response = requests.get(
                "https://api.linkedin.com/v2/memberSnapshotData",
                headers=headers,
                params={"q": "memberAndApplication"}
            )
            
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error Response: {response.text}")
                return {"error": f"API Error: {response.status_code}", "details": response.text}
                
        except Exception as e:
            print(f"Error calling Member Data Portability API: {e}")
            return {"error": "Failed to fetch data", "details": str(e)}


@app.route("/test", methods=["GET"])
def test():
    global access_token
    if access_token == None:
        return {"error": "No access token available"}
    else:
        return {"access_token": "***" if access_token else "None"}


@app.route("/oauth", methods=["GET"])
def oauth():
    global access_token

    args = request.args
    auth_code = args.get("code")

    if auth_code:
        token_response = auth_client.exchange_auth_code_for_access_token(auth_code)
        access_token = token_response.access_token
        print(f"Access token: {access_token}")
        return redirect("/")


if __name__ == "__main__":
    app.run(host="localhost", port=3000)
