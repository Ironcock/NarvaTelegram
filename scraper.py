import os
import json
import requests
import time
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION (I added your details here) ---
TELEGRAM_TOKEN = "8589217491:AAFGEOhRyEXZ9EzviIZ-QaM1eQT4w-fdJ1U"
TELEGRAM_CHAT_ID = "-1003535100197"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 

HISTORY_FILE = "history.json"

# Configure AI
if not GEMINI_API_KEY:
    print("❌ ERROR: Gemini API Key is missing! Please set it in GitHub Secrets or paste it in the script.")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# --- HELPERS ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w') as f: json.dump(history, f, indent=2)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: 
        r = requests.post(url, json=payload)
        if r.status_code != 200: print(f"Telegram Error: {r.text}")
    except Exception as e: print(f"Telegram Connection Fail: {e}")

def translate_to_russian(text):
    prompt = f"Translate to Russian (HTML format, no markdown, no <br>). Keep meaning. Text: {text[:3000]}"
    try:
        response = model.generate_content(prompt)
        return response.text.replace('```html', '').replace('```', '')
    except:
        return text

# --- SCRAPER: SETI.EE ---
def check_seti(history):
    print("Checking Seti.ee...")
    new_ids = []
    try:
        r = requests.get("https://www.magazin.seti.ee/modules/Board/index.php?pa=view&cid=33", headers={'User-Agent': 'Mozilla/5.0'})
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        links = soup.select('a[href*="viewannonces"]')[:10]
        
        for link in links:
            href = link.get('href')
            if not href.startswith('http'): href = "https://www.magazin.seti.ee/modules/Board/" + href
            job_id = href 
            
            if job_id not in history.get('seti', []):
                title = link.get_text(strip=True)
                print(f"New Seti: {title}")
                
                # Fetch Description
                desc_r = requests.get(href, headers={'User-Agent': 'Mozilla/5.0'})
                desc_r.encoding = 'utf-8'
                desc_soup = BeautifulSoup(desc_r.text, 'html.parser')
                desc_text = desc_soup.get_text(separator="\n", strip=True)[:1000]
                
                ru_text = translate_to_russian(f"{title}\n\n{desc_text}")
                send_telegram(f"<a href='{href}'>SETI.EE</a>\n\n{ru_text}")
                new_ids.append(job_id)
                time.sleep(2)
                
    except Exception as e:
        print(f"Error Seti: {e}")
    
    if new_ids:
        history.setdefault('seti', []).extend(new_ids)
        return True
    return False

# --- SCRAPER: CVKESKUS ---
def check_cvkeskus(history):
    print("Checking CVKeskus...")
    new_ids = []
    try:
        r = requests.get("https://www.cvkeskus.ee/toopakkumised?op=search&search%5Blocations%5D%5B%5D=6&sort=activation_date", headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.content, 'html.parser')
        jobs = soup.select('a.jobad-url')[:5]

        for job in jobs:
            href = job.get('href')
            if not href.startswith('http'): href = 'https://www.cvkeskus.ee' + href
            job_id = href.split('-')[-1]

            if job_id not in history.get('cvkeskus', []):
                title = job.find('h2').text.strip() if job.find('h2') else "Job"
                print(f"New CVKeskus: {title}")
                
                # Fetch details
                d_r = requests.get(href, headers={'User-Agent': 'Mozilla/5.0'})
                d_soup = BeautifulSoup(d_r.content, 'html.parser')
                desc = d_soup.select_one('.job-offer')
                desc_text = desc.get_text(strip=True)[:1500] if desc else "Click link for details"
                
                ru_text = translate_to_russian(f"{title}\n{desc_text}")
                send_telegram(f"<a href='{href}'>CVKESKUS</a>\n\n{ru_text}")
                new_ids.append(job_id)
                time.sleep(2)

    except Exception as e:
        print(f"Error CVKeskus: {e}")

    if new_ids:
        history.setdefault('cvkeskus', []).extend(new_ids)
        return True
    return False

# --- SCRAPER: TOOTUKASSA ---
def check_tootukassa(history):
    print("Checking Tootukassa...")
    new_ids = []
    try:
        url = "https://www.tootukassa.ee/web/graphql"
        query = {
            "operationName": "jobOfferSearch",
            "variables": {"first": 50, "searchInput": {}},
            "query": "query jobOfferSearch($first: Int, $searchInput: InputToopakkumineAvalikOtsingDTO) { jobOffersQuery(first: $first, searchInput: $searchInput) { edges { id nimetus alias aadressid } } }"
        }
        r = requests.post(url, json=query)
        jobs = r.json()['data']['jobOffersQuery']['edges']

        for job in jobs:
            # Narva Filter
            addrs = [str(a).lower() for a in job.get('aadressid', []) if a]
            is_narva = False
            for a in addrs:
                if 'narva' in a and 'narva mnt' not in a and 'tallinn' not in a:
                    is_narva = True
                    break
            
            if is_narva:
                job_id = str(job['id'])
                if job_id not in history.get('tootukassa', []):
                    title = job['nimetus']
                    print(f"New Tootukassa: {title}")
                    link = f"https://www.tootukassa.ee/et/toopakkumised/{job['alias']}"
                    
                    ru_text = translate_to_russian(f"{title}\nSee details at link.")
                    send_telegram(f"<a href='{link}'>TÖÖTUKASSA</a>\n\n{ru_text}")
                    new_ids.append(job_id)

    except Exception as e:
        print(f"Error Tootukassa: {e}")

    if new_ids:
        history.setdefault('tootukassa', []).extend(new_ids)
        return True
    return False

if __name__ == "__main__":
    history = load_history()
    c1 = check_seti(history)
    c2 = check_cvkeskus(history)
    c3 = check_tootukassa(history)
    
    # Save if changes
    if c1 or c2 or c3:
        # Keep list short
        for k in history: history[k] = history[k][-50:]
        save_history(history)
        print("History updated.")
    else:
        print("No new jobs.") 
