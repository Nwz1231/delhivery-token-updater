import requests
import base64
import hashlib
import secrets
import re
import os
from bs4 import BeautifulSoup

# ---------------- CONFIG ----------------
CLIENT_ID = "ucp-vue-frontend"
REDIRECT_URI = "https://one.delhivery.com/v2/dashboard"

GSHEET_WEBAPP_URL = os.environ.get("GSHEET_WEBAPP_URL")

# ---------------- ACCOUNTS ----------------
ACCOUNTS = {
    "sello": {
        "username": "customercare@selloship.com",
        "password": "Customer@12345",
        "tenant": 1,
        "sheet_cell": "A1"
    },
    "delhiveryB": {
        "username": "cartpein@gmail.com",
        "password": "Qazxsw@123456",
        "tenant": 0,
        "sheet_cell": "A2"
    }
}

# ---------------- TOKEN GENERATOR ----------------
def generate_token(username, password, tenant_index):
    s = requests.Session()

    # 1️⃣ Tenant discovery
    r = s.get(f"https://ucp-app-auth.delhivery.com/p/tenants?email={username}")
    r.raise_for_status()
    tenants = r.json()

    if tenant_index >= len(tenants):
        raise Exception("Invalid tenant index")

    realm = tenants[tenant_index]["keycloak_realm"]
    print(f"🔐 Using realm: {realm}")

    # 2️⃣ PKCE
    code_verifier = base64.urlsafe_b64encode(
        secrets.token_bytes(64)
    ).rstrip(b"=").decode()

    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    # 3️⃣ Auth request
    auth_url = (
        f"https://ucp-auth.delhivery.com/realms/{realm}/protocol/openid-connect/auth"
        f"?client_id={CLIENT_ID}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&login_hint={username}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=openid"
    )

    r = s.get(auth_url)
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")

    if not form:
        raise Exception("Login form not found (OTP/CAPTCHA enabled)")

    login_url = form["action"]
    if login_url.startswith("/"):
        login_url = f"https://ucp-auth.delhivery.com{login_url}"

    # 4️⃣ Submit credentials
    r = s.post(
        login_url,
        data={"username": username, "password": password, "credentialId": ""},
        allow_redirects=False
    )

    if "Location" not in r.headers:
        raise Exception("Login failed")

    # 5️⃣ Extract auth code
    match = re.search(r"code=([^&]+)", r.headers["Location"])
    if not match:
        raise Exception("Auth code missing")

    auth_code = match.group(1)

    # 6️⃣ Token exchange
    token_url = f"https://ucp-auth.delhivery.com/realms/{realm}/protocol/openid-connect/token"
    r = s.post(token_url, data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code": auth_code,
        "code_verifier": code_verifier
    })
    r.raise_for_status()

    tokens = r.json()
    return tokens.get("refresh_token")

# ---------------- PUSH TO SHEET ----------------
def push_to_sheet(token, account_name, cell):
    payload = {
        "account": account_name,
        "cell": cell,
        "refresh_token": token
    }
    r = requests.post(GSHEET_WEBAPP_URL, json=payload, timeout=15)
    r.raise_for_status()
    print(f"📤 Token pushed for {account_name} → {cell}")

# ---------------- MAIN ----------------
def main():
    for name, acc in ACCOUNTS.items():
        print(f"\n🔑 Generating token for {name}")
        refresh_token = generate_token(
            acc["username"],
            acc["password"],
            acc["tenant"]
        )

        if not refresh_token:
            print(f"❌ No token generated for {name}")
            continue

        push_to_sheet(refresh_token, name, acc["sheet_cell"])

    print("\n✅ ALL TOKENS GENERATED & PUSHED")

if __name__ == "__main__":
    main()
