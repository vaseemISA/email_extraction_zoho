import requests
import json
import time
import threading
from queue import Queue
import os
from dotenv import load_dotenv
from helper import send_admin_alert,sanitize_sensitive_numbers,build_full_quoted_thread,remove_quote
import re
from bs4 import BeautifulSoup
import html
from slm import analyze_thread_single_call
from agent import analyze_ticket_with_caching

load_dotenv()

# ---------------- CONFIG ----------------
CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
ORG_ID = os.getenv("ZOHO_ORG_ID")
REGION_DOMAIN = os.getenv("ZOHO_REGION_DOMAIN", "https://desk.zoho.com")

TOKEN_FILE = "zoho_access.json"
EXTRACT_FOLDER = "extracted_tickets"
os.makedirs(EXTRACT_FOLDER, exist_ok=True)




MAX_QUEUE_SIZE = 5        # process 5 tickets at a time
PAGE_LIMIT = 100          # fetch up to 100 tickets per Zoho call
SCAN_INTERVAL = 60        # 60 sec




# -------- TOKEN HANDLING --------
def load_access_token():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f).get("access_token", "")
        except Exception:
            return ""
    return ""


def save_access_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": token}, f)


def refresh_access_token():
    print("🔄 Access token expired — refreshing...")
    url = "https://accounts.zoho.com/oauth/v2/token"
    data = {
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
    }

    r = requests.post(url, data=data)
    try:
        res = r.json()
    except Exception:
        print("❌ Failed token refresh:", r.text)
        return None

    if "access_token" in res:
        new_token = res["access_token"]
        save_access_token(new_token)
        print("✓ Token refreshed")
        return new_token

    print("❌ Failed token refresh:", res)
    return None


# -------- HTML CLEANING --------
def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator="\n")
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\n{2,}", "\n\n", cleaned).strip()
    return cleaned


# -------- MAIN API CLASS --------
class ZohoDeskAPI:
    def __init__(self):
        self.org_id = ORG_ID
        self.base_url = f"{REGION_DOMAIN}/api/v1"

    def request(self, url, params=None):
        token = load_access_token()
        headers = {"Authorization": f"Zoho-oauthtoken {token}", "orgId": self.org_id}
        res = requests.get(url, headers=headers, params=params)

        if res.status_code == 401:
            token = refresh_access_token()
            if not token:
                return {"error": "token_refresh_failed"}
            headers["Authorization"] = f"Zoho-oauthtoken {token}"
            res = requests.get(url, headers=headers, params=params)

        try:
            return res.json()
        except Exception:
            return {"error": "invalid_json", "raw": res.text}

    def list_tickets(self, status="Open", offset=0, limit=100):
        url = f"{self.base_url}/tickets"
        params = {
            "status": status,
            "from": offset,
            "limit": limit,
            "sortBy": "-customerResponseTime"  # newest customer first
        }
        data = self.request(url, params)
        return data.get("data", []) if isinstance(data, dict) else []


    def post_request(self, url, data=None):
        token = load_access_token()
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "orgId": self.org_id,
            "Content-Type": "application/json",
        }
        res = requests.post(url, headers=headers, json=data)

        if res.status_code == 401:
            token = refresh_access_token()
            if not token:
                return {"error": "token_refresh_failed"}
            headers["Authorization"] = f"Zoho-oauthtoken {token}"
            res = requests.post(url, headers=headers, json=data)

        try:
            return res.json()
        except Exception:
            return {"error": "invalid_json", "raw": res.text}

    # -------- FULL CONTENT FETCH --------
    def get_latest_inbound(self, ticket_id):
        url = f"{self.base_url}/tickets/{ticket_id}/latestThread"
        params = {
            "needIncomingThread": True,
            "needPublic": True,
            "include": "plainText"
        }
        return self.request(url, params)

    def get_thread_body(self, ticket_id, thread_id):
        url = f"{self.base_url}/tickets/{ticket_id}/threads/{thread_id}"
        params = {"include": "plainText"}
        return self.request(url, params)

    def get_open_tickets(self, limit=50):
        url = f"{self.base_url}/tickets"
        params = {"limit": limit, "status": "Open"}
        data = self.request(url, params)
        return data.get("data", []) if isinstance(data, dict) else []

    def get_ticket_details(self, ticket_id):
        return self.request(f"{self.base_url}/tickets/{ticket_id}")

    def get_ticket_threads(self, ticket_id):
        return self.request(f"{self.base_url}/tickets/{ticket_id}/threads")

    def reply_to_ticket(self, ticket_id, thread_id, reply_content, from_email=None, to_email=None):
        url = f"{self.base_url}/tickets/{ticket_id}/sendReply"
        data = {
            "channel": "EMAIL",
            "isForward": False,
            "inReplyToThreadId": thread_id,  # attach reply to latest inbound
            "isPrivate": False,              # true = private note (no email sent)
            "contentType": "html",
            "content": reply_content,
        }
        if from_email:
            data["fromEmailAddress"] = from_email
        if to_email:
            data["to"] = to_email
        return self.post_request(url, data)

    def update_ticket_status(self, ticket_id, status):
        url = f"{self.base_url}/tickets/{ticket_id}"
        data = {"status": status}
        headers = {
            "Authorization": f"Zoho-oauthtoken {load_access_token()}",
            "orgId": self.org_id,
            "Content-Type": "application/json",
        }
        res = requests.patch(url, headers=headers, json=data)
        try:
            return res.json()
        except Exception:
            return {"error": "invalid_json", "raw": res.text}


# -------- QUEUE SYSTEM --------
class TicketQueueSystem:
    def __init__(self, zoho_api):
        self.zoho_api = zoho_api
        self.ticket_queue = Queue()
        self.stop_flag = False
        self.offset = 0          # pagination pointer
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._scan_loop, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        print("🚀 Ticket queue started — checking every 60 secs")

    def stop(self):
        self.stop_flag = True

    # ===========================
    # SCAN — add tickets to queue
    # ===========================
    def _scan_loop(self):
        while not self.stop_flag:
            try:
                # only refill queue if < MAX_QUEUE_SIZE
                if self.ticket_queue.qsize() < MAX_QUEUE_SIZE:
                    self._load_next_tickets()
            except Exception as e:
                print(f"⚠ Scan error: {e}")
            time.sleep(SCAN_INTERVAL)

    def _load_next_tickets(self):
        print("🔍 Fetching ticket batch...")
        tickets = self.zoho_api.list_tickets(status="Open", offset=self.offset, limit=PAGE_LIMIT)

        if not tickets:
            # restart pagination from beginning
            self.offset = 0
            print("🔁 Reached end of ticket list — restarting pagination")
            return

        for t in tickets:
            if self.ticket_queue.qsize() >= MAX_QUEUE_SIZE:
                break

            ticket_id = t.get("id")
            if not ticket_id:
                continue

            self.ticket_queue.put(ticket_id)
            print(f"➕ Queued #{ticket_id}")

        # move pagination forward only after loading a batch
        self.offset += PAGE_LIMIT

    # ===========================
    # WORKER — process ticket
    # ===========================
    def _worker(self):
        while not self.stop_flag:
            ticket_id = self.ticket_queue.get()
            try:
                self._process_ticket(ticket_id)
            except Exception as e:
                print(f"❌ Error handling ticket #{ticket_id}: {e}")
            finally:
                self.ticket_queue.task_done()
            time.sleep(1)



    def _process_ticket(self, ticket_id):
        ticket_details = self.zoho_api.get_ticket_details(ticket_id)
        if not ticket_details or ticket_details.get("error"):
            print(f"⚠ No valid ticket #{ticket_id}")
            return

        customer_email = ticket_details.get("email")

        latest = self.zoho_api.get_latest_inbound(ticket_id)
        if not latest or latest.get("error"):
            print(f"⚠ No inbound thread for #{ticket_id}")
            return

        inbound_time = latest.get("createdTime", "")
        reply_to_thread_id = latest.get("id")
        body_text = (latest.get("plainText") or latest.get("content") or "").strip()

        if not body_text:
            print(f"⏩ Skipped – no body for #{ticket_id}")
            return

        # skip auto replies
        auto_phrases = ["auto reply", "out of office", "automatic reply"]
        if any(p in body_text.lower() for p in auto_phrases):
            print(f"⏩ Skipped auto-reply for #{ticket_id}")
            return

        # skip duplicate inbound messages across restarts
        os.makedirs("last_inbound", exist_ok=True)
        inbound_file = os.path.join("last_inbound", f"{ticket_id}.txt")
        if os.path.exists(inbound_file) and open(inbound_file).read() == inbound_time:
            print(f"⏩ No new customer reply for #{ticket_id}")
            return
        open(inbound_file, "w").write(inbound_time)

        # fetch full thread history
        threads = self.zoho_api.get_ticket_threads(ticket_id)

        inbound_messages = []
        if threads and isinstance(threads, dict) and "data" in threads:
            for t in threads["data"]:
                if t.get("direction") == "in":  # inbound only
                    msg_date = t.get("createdTime", "")
                    thread_id = t.get("id")

                    body_data = self.zoho_api.get_thread_body(ticket_id, thread_id)
                    text = (body_data.get("plainText") if isinstance(body_data, dict) else "") or t.get("content", "")
                    text_clean = text.strip()
                    #pattern = r'On\s+\w{3},\s+\d{1,2}\s+\w{3},\s+\d{4},\s+\d{1,2}:\d{2}\s+.+?wrote:?'
                    #text_clean = re.split(pattern, text_clean, flags=re.IGNORECASE)[0].strip()
                    #text_clean = sanitize_sensitive_numbers(text_clean)
                    text_clean = remove_quote(text_clean)



                    # 🚨 keep ALL inbound messages, even thank-you or ok (your request)
                    if text_clean:
                        inbound_messages.append({
                            "email_date": msg_date,
                            "email_content": text_clean
                        })

        # sort oldest → latest
        inbound_messages.sort(key=lambda x: x["email_date"])

        thread_json = {
            "ticket_id": ticket_id,
            "customer_email": customer_email,
            "subject": ticket_details.get("subject", ""),
            "messages": inbound_messages
        }

        # save JSON
        filename = os.path.join(EXTRACT_FOLDER, f"ticket_{ticket_id}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(thread_json, f, indent=4, ensure_ascii=False)

        print(f"💾 Saved extracted JSON → {filename}")

        print(f"🤖 Running LLM for #{ticket_id}")
        llm_result = analyze_ticket_with_caching(thread_json)
        reply_msg = llm_result.get("msg", "").replace("\n", "<br>").strip()
        reply_type = llm_result.get("type", "")

        if not reply_msg:
            print(f"⏩ No reply generated for #{ticket_id}")
            return
        if reply_type == "non_valid":
            print(f"⭐ Not booking-related – ignored #{ticket_id}")
            return
        # Build full thread history
        #quoted_thread = build_full_quoted_thread(threads, ticket_id, self.zoho_api)
        # Combine: New reply + Full history
        #full_reply = reply_msg + quoted_thread
        # send reply
        print(f"📨 Replying to #{ticket_id}...")
        self.zoho_api.reply_to_ticket(
            ticket_id=ticket_id,
            thread_id=reply_to_thread_id,
            reply_content=reply_msg,
            from_email=os.getenv("ZOHO_AGENT_EMAIL"),
            to_email=customer_email
        )

        print(f"📩 Reply sent to #{ticket_id}")

        # auto close if complete
        if reply_type == "present":
            self.zoho_api.update_ticket_status(ticket_id, "Closed")
            print(f"🔒 Closed #{ticket_id}")
        else:
            print(f"⏳ Awaiting customer response for #{ticket_id}")



    def get_queue_size(self):
        return self.ticket_queue.qsize()

    def get_processed_count(self):
        return len(self.processed_tickets)
