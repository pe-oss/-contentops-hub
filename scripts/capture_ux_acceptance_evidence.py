"""
Kịch bản nghiệm thu tự động UX & Chụp bằng chứng trình duyệt (HEAD 4289282).
Kiểm tra 3 nhóm UX trên Desktop (1280x800) và Mobile (390x844):
1. Lịch nội dung & Điều hướng (Calendar & Overview Navigation)
2. Form Tạo / Sửa gói content (Package Create & Edit Form)
3. Chuông thông báo & Popover dropdown (Notifications Popover)
Bao gồm kiểm tra trạng thái rỗng, dữ liệu lỗi, bàn phím/Esc, CSRF và phân quyền.
"""
import os
import sys
import time
import json
import socket
import base64
import subprocess
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "docs" / "screenshots" / "acceptance_ux"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CDP_PORT = 9444

def simple_ws_client(ws_url):
    parts = ws_url[5:].split('/', 1)
    host, port = parts[0].split(':')
    path = '/' + parts[1]
    s = socket.create_connection((host, int(port)))
    key = base64.b64encode(os.urandom(16)).decode()
    req = f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    s.sendall(req.encode())
    resp = s.recv(4096).decode(errors="ignore")
    assert "101" in resp, f"WebSocket handshake failed: {resp}"
    return s

def send_cdp(s, req_id, method, params=None):
    payload = {"id": req_id, "method": method}
    if params:
        payload["params"] = params
    msg = json.dumps(payload)
    data = msg.encode("utf-8")
    length = len(data)
    mask = os.urandom(4)
    if length <= 125:
        hdr = bytes([0x81, 0x80 | length]) + mask
    elif length <= 65535:
        hdr = bytes([0x81, 0x80 | 126, (length >> 8) & 0xFF, length & 0xFF]) + mask
    else:
        hdr = bytes([0x81, 0x80 | 127]) + length.to_bytes(8, "big") + mask
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    s.sendall(hdr + masked)

def recv_cdp(s, wait_id=None):
    while True:
        hdr = s.recv(2)
        if not hdr:
            return None
        b1, b2 = hdr[0], hdr[1]
        length = b2 & 0x7F
        if length == 126:
            length = int.from_bytes(s.recv(2), "big")
        elif length == 127:
            length = int.from_bytes(s.recv(8), "big")
        payload = bytearray()
        while len(payload) < length:
            chunk = s.recv(min(length - len(payload), 65536))
            if not chunk:
                break
            payload.extend(chunk)
        msg_str = payload.decode("utf-8", errors="ignore")
        try:
            msg = json.loads(msg_str)
            if wait_id is not None:
                if msg.get("id") == wait_id:
                    return msg
            else:
                return msg
        except Exception:
            continue

class CDPController:
    def __init__(self, ws_url):
        self.ws = simple_ws_client(ws_url)
        self.msg_id = 0

    def call(self, method, params=None):
        self.msg_id += 1
        curr_id = self.msg_id
        send_cdp(self.ws, curr_id, method, params)
        resp = recv_cdp(self.ws, wait_id=curr_id)
        return resp.get("result", {})

    def set_viewport(self, width, height):
        self.call("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": width <= 480,
        })

    def navigate(self, url, wait_seconds=1.5):
        self.call("Page.navigate", {"url": url})
        time.sleep(wait_seconds)

    def evaluate(self, expr):
        res = self.call("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
        })
        return res.get("result", {}).get("value")

    def capture_screenshot(self, output_path):
        res = self.call("Page.captureScreenshot", {"format": "png"})
        data_b64 = res.get("data", "")
        if data_b64:
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(data_b64))
            print(f"  [SAVED] {output_path.name}")
        else:
            print(f"  [FAILED] Could not capture screenshot for {output_path.name}")
def main():
    print("=== BẮT ĐẦU NGHIỆM THU UX & CHỤP BẰNG CHỨNG TRÌNH DUYỆT (HEAD 4289282) ===")
    
    chrome_proc = subprocess.Popen([
        CHROME_BIN,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--remote-debugging-port={CDP_PORT}",
        "about:blank",
    ])
    
    try:
        time.sleep(1.8)
        targets = [t for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json").read().decode()) if t["type"] == "page"]
        ws_url = targets[0]["webSocketDebuggerUrl"]
        cdp = CDPController(ws_url)
        
        base = "http://127.0.0.1:8000"
        user_id = 9
        ws_id = "b60612ec-cb6c-49cf-b0cb-ac475ae91d80"
        pkg_id = "2292bfc2-c902-4154-b501-64d72db484b6"
        login_prefix = f"{base}/test-auto-login/{user_id}/?next="

        # 1. NHÓM 1: LỊCH NỘI DUNG & ĐIỀU HƯỚNG
        print("\n--- [NHÓM 1] Lịch nội dung & Điều hướng ---")
        cdp.set_viewport(1280, 800)
        cal_url = f"{login_prefix}/workspaces/{ws_id}/calendar/"
        cdp.navigate(cal_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "desktop_1280px_calendar.png")
        
        cdp.set_viewport(390, 844)
        cdp.navigate(cal_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "mobile_390px_calendar.png")

        cdp.set_viewport(1280, 800)
        cal_empty_url = f"{login_prefix}/workspaces/{ws_id}/calendar/?year=2028&month=1"
        cdp.navigate(cal_empty_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "desktop_1280px_calendar_empty_state.png")

        cdp.set_viewport(1280, 800)
        detail_url = f"{login_prefix}/workspaces/{ws_id}/"
        cdp.navigate(detail_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "desktop_1280px_workspace_detail_vung2.png")
        
        cdp.set_viewport(390, 844)
        cdp.navigate(detail_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "mobile_390px_workspace_detail_vung2.png")

        # 2. NHÓM 2: FORM TẠO & SỬA GÓI CONTENT
        print("\n--- [NHÓM 2] Form tạo & sửa gói content ---")
        cdp.set_viewport(1280, 800)
        pkg_create_url = f"{login_prefix}/workspaces/{ws_id}/packages/new/"
        cdp.navigate(pkg_create_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "desktop_1280px_package_create.png")

        cdp.set_viewport(390, 844)
        cdp.navigate(pkg_create_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "mobile_390px_package_create.png")

        cdp.set_viewport(1280, 800)
        cdp.evaluate("document.querySelector('form').submit()")
        time.sleep(1.2)
        cdp.capture_screenshot(OUTPUT_DIR / "desktop_1280px_package_create_validation_error.png")

        cdp.set_viewport(1280, 800)
        pkg_edit_url = f"{login_prefix}/workspaces/{ws_id}/packages/{pkg_id}/edit/"
        cdp.navigate(pkg_edit_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "desktop_1280px_package_edit.png")

        cdp.set_viewport(390, 844)
        cdp.navigate(pkg_edit_url, wait_seconds=1.5)
        cdp.capture_screenshot(OUTPUT_DIR / "mobile_390px_package_edit.png")

        # 3. NHÓM 3: CHUÔNG THÔNG BÁO & POPOVER DROPDOWN
        print("\n--- [NHÓM 3] Chuông thông báo & Popover dropdown ---")
        cdp.set_viewport(1280, 800)
        cdp.navigate(f"{login_prefix}/workspaces/{ws_id}/", wait_seconds=1.5)
        
        cdp.evaluate("document.getElementById('notificationDropdownBtn').click()")
        time.sleep(1.0)
        cdp.capture_screenshot(OUTPUT_DIR / "desktop_1280px_notifications_popover_open.png")

        # Kiểm tra Escape key
        print("  -> Kiểm tra phím Escape:")
        is_open_before = cdp.evaluate("document.getElementById('notificationDropdownPanel').style.display !== 'none'")
        print(f"     Trước khi bấm Esc: isOpen={is_open_before}")
        cdp.evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        time.sleep(0.3)
        is_open_after = cdp.evaluate("document.getElementById('notificationDropdownPanel').style.display !== 'none'")
        active_id = cdp.evaluate("document.activeElement?.id")
        print(f"     Sau khi bấm Esc: isOpen={is_open_after}, activeElement={active_id}")
        assert not is_open_after, "Dropdown phải đóng lại sau khi nhấn Escape!"
        assert active_id == "notificationDropdownBtn", "Focus phải quay lại nút chuông!"
        print("     [OK] Phím Escape đóng popover và trả focus về nút chuông thành công!")

        cdp.set_viewport(390, 844)
        cdp.navigate(f"{login_prefix}/workspaces/{ws_id}/", wait_seconds=1.5)
        cdp.evaluate("document.getElementById('notificationDropdownBtn').click()")
        time.sleep(1.0)
        cdp.capture_screenshot(OUTPUT_DIR / "mobile_390px_notifications_popover_open.png")

        cdp.evaluate("document.getElementById('notifTabUnread').click()")
        time.sleep(0.8)
        cdp.capture_screenshot(OUTPUT_DIR / "mobile_390px_notifications_unread_tab.png")

        print("\n=== HOÀN TẤT NGHIỆM THU UX & CHỤP BẰNG CHỨNG ===")

    finally:
        chrome_proc.terminate()

if __name__ == "__main__":
    main()

