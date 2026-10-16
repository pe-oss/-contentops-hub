import re
import sys
import requests

BASE_URL = "http://127.0.0.1:8088"
session = requests.Session()

print(f"1. Testing Root and Static...")
r_root = session.get(f"{BASE_URL}/")
assert r_root.status_code == 200, f"Root returned {r_root.status_code}"
print("   - Root page: 200 OK")

r_css = session.get(f"{BASE_URL}/static/css/app.css")
assert r_css.status_code == 200, f"App CSS returned {r_css.status_code}"
assert "body" in r_css.text or "{" in r_css.text
print("   - App static CSS: 200 OK via WhiteNoise")

r_admin_css = session.get(f"{BASE_URL}/static/admin/css/base.css")
assert r_admin_css.status_code == 200, f"Admin CSS returned {r_admin_css.status_code}"
print("   - Admin static CSS: 200 OK via WhiteNoise")

print("2. Testing Auth: Registration and Login...")
r_reg_page = session.get(f"{BASE_URL}/auth/register/")
assert r_reg_page.status_code == 200
csrf_token = session.cookies.get("csrftoken")

username = "smoke_tester"
email = "smoketester@example.com"
password = "SmokeTestPassword2026!"

reg_data = {
    "csrfmiddlewaretoken": csrf_token,
    "first_name": "Nguyen",
    "last_name": "Tester",
    "username": username,
    "email": email,
    "password1": password,
    "password2": password,
    "terms": "on",
}
headers = {"Referer": f"{BASE_URL}/auth/register/"}
r_reg = session.post(f"{BASE_URL}/auth/register/", data=reg_data, headers=headers)
print(f"   - Registration response: {r_reg.status_code} -> final url: {r_reg.url}")
assert r_reg.status_code == 200 and "/dashboard" in r_reg.url, f"Registration failed, url: {r_reg.url}"
print("   - Registered and auto-logged in to dashboard successfully!")

# Test Login explicitly as well
session_login = requests.Session()
r_login_page = session_login.get(f"{BASE_URL}/auth/login/")
csrf_token_login = session_login.cookies.get("csrftoken")
login_data = {
    "csrfmiddlewaretoken": csrf_token_login,
    "username": email,
    "password": password,
}
headers_login = {"Referer": f"{BASE_URL}/auth/login/"}
r_login = session_login.post(f"{BASE_URL}/auth/login/", data=login_data, headers=headers_login)
print(f"   - Explicit Login response: {r_login.status_code} -> final url: {r_login.url}")
assert r_login.status_code == 200 and "/dashboard" in r_login.url, f"Login failed: {r_login.url}"
print("   - Explicit Email login verified 200 OK on Dashboard!")

print("3. Testing Read / Write Data Flow (Workspace creation)...")
r_ws_new = session.get(f"{BASE_URL}/workspaces/new/")
assert r_ws_new.status_code == 200
csrf_token_ws = session.cookies.get("csrftoken")
ws_data = {
    "csrfmiddlewaretoken": csrf_token_ws,
    "name": "Smoke Test Workspace 01",
    "timezone": "Asia/Ho_Chi_Minh",
}
headers_ws = {"Referer": f"{BASE_URL}/workspaces/new/"}
r_ws_create = session.post(f"{BASE_URL}/workspaces/new/", data=ws_data, headers=headers_ws)
print(f"   - Workspace creation: {r_ws_create.status_code} -> final url: {r_ws_create.url}")
assert r_ws_create.status_code == 200 and "/workspaces/" in r_ws_create.url, f"Workspace create failed: {r_ws_create.url}"
assert "Smoke Test Workspace 01" in r_ws_create.text
print("   - Workspace 'Smoke Test Workspace 01' created and read back successfully!")

# Check dashboard reflects workspace
r_dash = session.get(f"{BASE_URL}/dashboard/")
assert "Smoke Test Workspace 01" in r_dash.text
print("   - Dashboard reflects created workspace successfully!")

print("\n=== ALL SMOKE CHECKS PASSED PERFECTLY! ===")

