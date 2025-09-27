import requests
import secrets
import hashlib
import base64
import re
from bs4 import BeautifulSoup   # pip install beautifulsoup4
import os

EMAIL = "customercare@selloship.com"
PASSWORD = "Customer@1234"
CLIENT_ID = "ucp-vue-frontend"
REDIRECT_URI = "https://one.delhivery.com/v2/dashboard"

s = requests.Session()

# Step 1: tenant discovery
r = s.get(f"https://ucp-app-auth.delhivery.com/p/tenants?email={EMAIL}")
realm = r.json()[1]["keycloak_realm"]  # private limited
print("Using realm:", realm)

# Step 2: PKCE
code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
challenge = hashlib.sha256(code_verifier.encode()).digest()
code_challenge = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode()

# Step 3: Get login form
auth_url = (
    f"https://ucp-auth.delhivery.com/realms/{realm}/protocol/openid-connect/auth"
    f"?client_id={CLIENT_ID}"
    f"&code_challenge={code_challenge}"
    f"&code_challenge_method=S256"
    f"&login_hint={EMAIL}"
    f"&redirect_uri={REDIRECT_URI}"
    f"&response_type=code"
    f"&scope=openid"
)

r = s.get(auth_url)
soup = BeautifulSoup(r.text, "html.parser")
form = soup.find("form")

if not form:
    raise Exception("Login form not found. Page changed?")

login_action_url = form["action"]
print("Real login action URL:", login_action_url)

# Step 4: Post credentials
payload = {
    "username": EMAIL,
    "password": PASSWORD,
    "credentialId": ""
}
r = s.post(login_action_url, data=payload, allow_redirects=False)

if "Location" not in r.headers:
    print("Login failed. Status:", r.status_code)
    print(r.text[:500])  # debug first 500 chars
    exit()

redirect_location = r.headers["Location"]
print("Redirected to:", redirect_location)

# Step 5: Extract auth code
match = re.search(r"code=([^&]+)", redirect_location)
if not match:
    raise Exception("Auth code not found in redirect")
auth_code = match.group(1)
print("Authorization Code:", auth_code)

# Step 6: Token exchange
token_url = f"https://ucp-auth.delhivery.com/realms/{realm}/protocol/openid-connect/token"
token_payload = {
    "grant_type": "authorization_code",
    "code": auth_code,
    "redirect_uri": REDIRECT_URI,
    "client_id": CLIENT_ID,
    "code_verifier": code_verifier,
}
r = s.post(token_url, data=token_payload)
tokens = r.json()
print("Access token:", tokens.get("access_token", "")[:50], "...")
print("Refresh token:", tokens.get("refresh_token", "")[:50], "...")

# ----------------------------------------------------------------
# Step 7: Push refresh token to Google Sheet via Apps Script Web App
# ----------------------------------------------------------------
refresh_token = tokens.get("refresh_token")
if refresh_token:
    webapp_url = os.environ.get("GSHEET_WEBAPP_URL")  # store in GitHub Secrets
    try:
        resp = requests.post(webapp_url, json={"refresh_token": refresh_token})
        print("Google Sheet update response:", resp.text)
    except Exception as e:
        print("Failed to update Google Sheet:", e)
else:
    print("No refresh token found to push.")