import os
import sys
import json
import time
import codecs
import argparse
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8589217491:AAFGEOhRyEXZ9EzviIZ-QaM1eQT4w-fdJ1U")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003535100197")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HISTORY_FILE = Path(__file__).parent / "history.json"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Configure AI
if not GEMINI_API_KEY:
    print("❌ ERROR: Gemini API Key is missing! Please set it in .env or GitHub Secrets.")
    sys.exit(1)

import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)


# --- HELPERS ---
def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def send_telegram(text, dry_run=False):
    if dry_run:
        print(f"\n[DRY RUN - NOT SENT TO TELEGRAM]:\n{text}\n")
        return True
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            print("  ✅ Sent to Telegram successfully!")
            return True
        else:
            print(f"  ❌ Telegram Error ({r.status_code}): {r.text}")
            return False
    except Exception as e:
        print(f"  ❌ Telegram Connection Fail: {e}")
        return False

def format_with_ai(title, content, source_name, url, is_russian=False):
    task_desc = "Отредактируй и оформи это объявление" if is_russian else "Переведи на русский язык и оформи вакансию"
    prompt = f"""
Ты — профессиональный редактор русскоязычного Telegram-канала с вакансиями в Нарве (Эстония).
{task_desc} в аккуратный, максимально информативный и удобный для чтения с телефона Telegram-пост.

Вакансия: {title}
Источник: {source_name}
Ссылка: {url}
Данные:
{content}

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА ОФОРМЛЕНИЯ:
1. Первая строка — четкий заголовок: <b>Название должности</b>
2. 🏢 <b>Работодатель:</b> Название компании или учреждения
3. 📍 <b>Адрес:</b> ОБЯЗАТЕЛЬНО укажи точный адрес или улицу (например: <code>г. Нарва, Aleksander Puškini 10</code> или <code>Peterburi mnt 1</code>), если есть. Если только город — напиши город.
4. 💰 <b>Зарплата:</b> ОБЯЗАТЕЛЬНО укажи сумму (например: <code>2330 € брутто</code>, <code>5 € / час</code>) и условия/надбавки. Если не указана — <code>По договоренности / не указана</code>.
5. ⏳ <b>Срок подачи заявки:</b> Точная дата (например: <code>до 16 октября 2026</code>), если указана.
6. ⏱️ <b>Занятость и график:</b> ОБЯЗАТЕЛЬНО укажи форму занятости (полная / частичная), посменно или нет, тип договора (бессрочный/срочный) и дату выхода на работу (если есть).
7. 🗣️ <b>Языковые требования:</b> ОБЯЗАТЕЛЬНО укажи четко требования ко ВСЕМ языкам из текста (например: <i>Эстонский не требуется, русский или английский (A2)</i> или <i>Эстонский (C1)</i>).
8. 🎓 <b>Образование и навыки:</b> ОБЯЗАТЕЛЬНО укажи требуемый уровень образования (основное, среднее, высшее) и владение компьютером (если есть).
9. 📋 <b>Обязанности:</b> 3-5 конкретных понятных пунктов.
10. 🎯 <b>Требования:</b> ключевые навыки, наличие сертификатов/справок (гигиена, медсправка, права).
11. 💼 <b>Условия / Предложение работодателя:</b> обучение, коллектив, отпуск, бонусы.
12. 📞 <b>Контакты:</b> 
    - ВСЕ телефоны: ОБЯЗАТЕЛЬНО в формате <code>+372XXXXXXXX</code> целиком, без пробелов, для копирования в один клик!
    - Email: <code>email@domain.ee</code>
13. В самом конце:
    🔗 <b>Источник:</b> <a href="{url}">{source_name}</a>

ВНИМАНИЕ:
- НИКАКИХ ХЕШТЕГОВ (хештеги запрещены!).
- Используй ТОЛЬКО Telegram HTML теги: <b>, <i>, <code>, <a>. Никакого Markdown (** или ##), никаких кодовых блоков ```html.
"""
    for model_name in ['gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-flash-latest']:
        try:
            m = genai.GenerativeModel(model_name)
            resp = m.generate_content(prompt)
            text = resp.text.strip().replace("```html", "").replace("```", "").strip()
            return text
        except Exception as e:
            print(f"  ⚠️ Model {model_name} error ({e}), trying fallback...")
            time.sleep(1)

    snippet = content.replace("<", "&lt;").replace(">", "&gt;")[:400]
    return f"<b>{title}</b>\n\n{snippet}...\n\n🔗 <b>Источник:</b> <a href='{url}'>{source_name}</a>"


# --- SCRAPER: SETI.EE ---
def check_seti(history, max_posts=1, dry_run=False):
    print("\n[1/3] Checking Seti.ee...")
    new_ids = []
    sent_count = 0
    try:
        r = requests.get("https://www.magazin.seti.ee/modules/Board/index.php?pa=view&cid=33", headers=HEADERS, timeout=10)
        r.encoding = r.apparent_encoding or 'windows-1251'
        soup = BeautifulSoup(r.text, 'html.parser')
        links = soup.select('a[href*="viewannonces"]')
        
        seen = set()
        for link in links:
            href = link.get('href')
            if not href.startswith('http'):
                href = "https://www.magazin.seti.ee/modules/Board/" + href
            if href in seen:
                continue
            seen.add(href)
            
            job_id = href
            if job_id not in history.get('seti', []):
                title = link.get_text(strip=True)
                if not title:
                    continue
                print(f"  New Seti ad: {title}")
                
                # Fetch details
                desc_text = ""
                try:
                    d_r = requests.get(href, headers=HEADERS, timeout=10)
                    d_r.encoding = d_r.apparent_encoding or 'windows-1251'
                    d_soup = BeautifulSoup(d_r.text, 'html.parser')
                    for t in d_soup.find_all('table'):
                        txt = t.get_text()
                        if 'Объявление' in txt and 'Детали объявления' not in txt:
                            desc_text = t.get_text(separator="\n", strip=True)
                            break
                    if not desc_text:
                        desc_text = d_soup.get_text(separator=" ", strip=True)[:500]
                except Exception as ex:
                    desc_text = f"Error: {ex}"
                
                formatted_post = format_with_ai(title, desc_text, "SETI.EE", href, is_russian=True)
                if send_telegram(formatted_post, dry_run=dry_run):
                    new_ids.append(job_id)
                    sent_count += 1
                    time.sleep(2.5)
                
                if sent_count >= max_posts:
                    break
    except Exception as e:
        print(f"  ❌ Error Seti: {e}")
        
    if new_ids:
        history.setdefault('seti', []).extend(new_ids)
        return True
    return False


# --- SCRAPER: CVKESKUS ---
def extract_cvkeskus_rich_data(job_url):
    """Fetches full job data from CVKeskus, including iframe content and JSON-LD schema."""
    s = requests.Session()
    s.headers.update(HEADERS)
    r = s.get(job_url, timeout=10)
    soup = BeautifulSoup(r.content, 'html.parser')
    
    # 1. Check for iframe
    ifr = soup.find('iframe', id='htmlContentIframe')
    iframe_text = ""
    if ifr and ifr.get('src'):
        src = ifr.get('src')
        full_ifr_url = "https://www.cvkeskus.ee" + src
        try:
            r_ifr = s.get(full_ifr_url, headers={'Referer': job_url}, timeout=10)
            if r_ifr.status_code == 200:
                soup_ifr = BeautifulSoup(r_ifr.content, 'html.parser')
                iframe_text = soup_ifr.get_text(separator="\n", strip=True)
        except Exception as e:
            print("  ⚠️ Iframe fetch error:", e)

    # 2. Check JSON-LD metadata for structured salary, deadline, company
    json_ld_data = {}
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'JobPosting':
                json_ld_data = data
                break
            elif isinstance(data, dict) and '@graph' in data:
                for item in data['@graph']:
                    if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                        json_ld_data = item
                        break
        except Exception:
            pass

    # 3. Regular container
    desc_container = soup.select_one('.job-offer, .jobad, article')
    container_text = desc_container.get_text(separator="\n", strip=True) if desc_container else ""

    salary = ""
    if json_ld_data.get('baseSalary'):
        bs = json_ld_data['baseSalary']
        val = bs.get('value', {})
        min_v = val.get('minValue') or val.get('value')
        max_v = val.get('maxValue')
        unit = "в месяц" if val.get('unitText') == 'MONTH' else (val.get('unitText') or "")
        if min_v and max_v:
            salary = f"{min_v} - {max_v} € {unit}"
        elif min_v:
            salary = f"{min_v} € {unit}"

    deadline = ""
    if json_ld_data.get('validThrough'):
        deadline = json_ld_data['validThrough'][:10]

    emp_type = ""
    if json_ld_data.get('employmentType'):
        et = json_ld_data['employmentType']
        emp_type = "полная занятость" if et == 'FULL_TIME' else ("частичная занятость" if et == 'PART_TIME' else et)

    combined = []
    if salary:
        combined.append(f"Указанная зарплата: {salary}")
    if deadline:
        combined.append(f"Срок подачи заявки (дедлайн): {deadline}")
    if emp_type:
        combined.append(f"Форма занятости: {emp_type}")
    if iframe_text:
        combined.append(f"Текст объявления:\n{iframe_text}")
    elif container_text:
        combined.append(f"Текст объявления:\n{container_text}")
    elif json_ld_data.get('description'):
        soup_desc = BeautifulSoup(json_ld_data['description'], 'html.parser')
        combined.append(f"Описание:\n{soup_desc.get_text(separator=' ', strip=True)}")

    return "\n\n".join(combined)

def check_cvkeskus(history, max_posts=1, dry_run=False):
    print("\n[2/3] Checking CVKeskus.ee...")
    new_ids = []
    sent_count = 0
    try:
        r = requests.get("https://www.cvkeskus.ee/toopakkumised?op=search&search%5Blocations%5D%5B%5D=6&sort=activation_date", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, 'html.parser')
        jobs = soup.select('a.jobad-url')
        
        seen = set()
        for job in jobs:
            href = job.get('href')
            if not href.startswith('http'):
                href = 'https://www.cvkeskus.ee' + href
            job_id = href.split('-')[-1]
            if job_id in seen:
                continue
            seen.add(job_id)
            
            if job_id not in history.get('cvkeskus', []):
                title_tag = job.find('h2')
                title = title_tag.text.strip() if title_tag else job.get_text(strip=True)
                if not title:
                    continue
                print(f"  New CVKeskus: {title}")
                
                rich_content = extract_cvkeskus_rich_data(href)
                if not rich_content:
                    rich_content = f"Amet: {title}\nVaata täpsemat infot lingilt."
                    
                formatted_post = format_with_ai(title, rich_content, "CVKESKUS", href, is_russian=False)
                if send_telegram(formatted_post, dry_run=dry_run):
                    new_ids.append(job_id)
                    sent_count += 1
                    time.sleep(2.5)
                    
                if sent_count >= max_posts:
                    break
    except Exception as e:
        print(f"  ❌ Error CVKeskus: {e}")
        
    if new_ids:
        history.setdefault('cvkeskus', []).extend(new_ids)
        return True
    return False


# --- SCRAPER: TOOTUKASSA ---
def fetch_tootukassa_details(job_id, addresses):
    """Fetches full job details from Tootukassa GraphQL API."""
    url = "https://www.tootukassa.ee/web/graphql"
    headers = {'User-Agent': HEADERS['User-Agent'], 'Content-Type': 'application/json'}
    q = """
    query jobofferquery($id: Int!) {
      publicJobOfferQuery(jobOfferId: $id) {
        id
        asutusId
        nimetus
        ametinimetusTapsustus
        kandideerimineKp
        toopakkujaBrand {
          nimi
        }
        avalikKontaktisik {
          nimi
          email
          ametikoht
          telefon
        }
        tookohaAndmed {
          onTaiskohaga
          onOsakohaga
          onVahetustega
          onOositi
          tooaegTapsustus
          toosuhteKestusKood
          tooylesanded
          omaltPooltPakume
          tootasuAlates
          tootasuKuni
          tootasuTapsustus
          onPalkAvalik
          tooleAsuminePaev
          tooleAsumineKuu
          tooleAsumineAasta
        }
        noudedKandidaadile {
          haridusTase
          arvutiOskusTase
          arvutiOskusTapsustus
          keeleoskused {
            keel
            keelKood
            taseKones
            onNoutud
          }
          juhiload
          nouded
          lisainfoKandideerijale
        }
      }
    }
    """
    try:
        r = requests.post(url, json={"query": q, "variables": {"id": int(job_id)}}, headers=headers, timeout=10)
        data = r.json().get('data', {}).get('publicJobOfferQuery')
        if not data:
            return ""
        
        # Employer name
        company_name = ""
        if data.get('toopakkujaBrand') and data['toopakkujaBrand'].get('nimi'):
            company_name = data['toopakkujaBrand']['nimi']
        elif data.get('asutusId'):
            q_emp = """
            query employerQuery($id: Int!) {
              employerQuery(toopakkujaId: $id) {
                nimi
              }
            }
            """
            r_emp = requests.post(url, json={"query": q_emp, "variables": {"id": data['asutusId']}}, headers=headers, timeout=5)
            emp_data = r_emp.json().get('data', {}).get('employerQuery')
            if emp_data and emp_data.get('nimi'):
                company_name = emp_data['nimi']
                
        contact = data.get('avalikKontaktisik') or {}
        contact_name = contact.get('nimi', '')
        contact_phone = contact.get('telefon', '')
        contact_email = contact.get('email', '')
        if contact_email:
            try:
                contact_email = codecs.decode(contact_email, 'rot_13')
            except Exception:
                pass
            
        work = data.get('tookohaAndmed') or {}
        tasks = work.get('tooylesanded', '')
        offers = work.get('omaltPooltPakume', '')
        reqs = (data.get('noudedKandidaadile') or {}).get('nouded', '')
        edu = (data.get('noudedKandidaadile') or {}).get('haridusTase', '')
        pc_skill = (data.get('noudedKandidaadile') or {}).get('arvutiOskusTase', '')
        
        # Language skills parsing
        langs_list = []
        has_estonian = False
        for l in (data.get('noudedKandidaadile') or {}).get('keeleoskused') or []:
            k = l.get('keel', '')
            level = l.get('taseKones', '')
            req_status = "обязательно" if l.get('onNoutud') else "желательно"
            langs_list.append(f"{k} ({level}, {req_status})")
            if 'eesti' in k.lower():
                has_estonian = True
        if not has_estonian:
            langs_list.append("эстонский язык: не требуется")

        # Schedule & Contract
        schedule_parts = []
        if work.get('onTaiskohaga'): schedule_parts.append("полная занятость (Täistööaeg)")
        if work.get('onOsakohaga'): schedule_parts.append("частичная занятость (Osaline tööaeg)")
        if work.get('onVahetustega'): schedule_parts.append("посменная работа (Vahetustega)")
        if work.get('onOositi'): schedule_parts.append("ночные смены")
        if work.get('toosuhteKestusKood') == 'TAHTAJATU': schedule_parts.append("бессрочный договор")
        elif work.get('toosuhteKestusKood'): schedule_parts.append(f"договор: {work.get('toosuhteKestusKood')}")
        if work.get('tooaegTapsustus'): schedule_parts.append(str(work.get('tooaegTapsustus')))

        deadline = data.get('kandideerimineKp', '')
        if deadline and len(deadline) >= 10:
            deadline = deadline[:10]
            
        start_date = ""
        if work.get('tooleAsuminePaev') and work.get('tooleAsumineKuu') and work.get('tooleAsumineAasta'):
            start_date = f"{work['tooleAsuminePaev']:02d}.{work['tooleAsumineKuu']:02d}.{work['tooleAsumineAasta']}"
        else:
            start_date = "Как можно скорее (Niipea kui võimalik)"
            
        salary = ""
        if work.get('onPalkAvalik') and (work.get('tootasuAlates') or work.get('tootasuKuni')):
            s_from = work.get('tootasuAlates', '')
            s_to = work.get('tootasuKuni', '')
            salary = f"{s_from} - {s_to} EUR" if s_from and s_to else f"от {s_from or s_to} EUR"
        elif work.get('tootasuTapsustus'):
            salary = work['tootasuTapsustus']
        else:
            salary = "По договоренности / не указана"

        summary = []
        if company_name: summary.append(f"Компания / Работодатель: {company_name}")
        summary.append(f"Должность: {data.get('nimetus')}")
        if addresses: summary.append(f"Точный адрес / Место работы: {', '.join(addresses)}")
        if salary: summary.append(f"Зарплата: {salary}")
        if deadline: summary.append(f"Срок подачи заявки (дедлайн): {deadline}")
        if schedule_parts: summary.append(f"Занятость и график: {', '.join(schedule_parts)}")
        if start_date: summary.append(f"Дата начала работы: {start_date}")
        if langs_list: summary.append(f"Требования к языкам: {'; '.join(langs_list)}")
        if edu: summary.append(f"Требуемое образование: {edu}")
        if pc_skill: summary.append(f"Компьютерные навыки: {pc_skill}")
        if tasks: summary.append(f"Обязанности:\n{tasks}")
        if reqs: summary.append(f"Требования:\n{reqs}")
        if offers: summary.append(f"Условия и предложения работодателя:\n{offers}")
        if contact_name or contact_phone or contact_email:
            summary.append(f"Контакты: {contact_name}, телефон: {contact_phone}, email: {contact_email}")
            
        return "\n\n".join(summary)
    except Exception as e:
        print(f"  ⚠️ Error fetching full Tootukassa details: {e}")
        return ""

def check_tootukassa(history, max_posts=1, dry_run=False):
    print("\n[3/3] Checking Töötukassa.ee...")
    new_ids = []
    sent_count = 0
    try:
        url = "https://www.tootukassa.ee/web/graphql"
        query = {
            "operationName": "jobOfferSearch",
            "variables": {
                "first": 50,
                "searchInput": {
                    "otsisona": "Narva"
                }
            },
            "query": "query jobOfferSearch($first: Int, $searchInput: InputToopakkumineAvalikOtsingDTO) { jobOffersQuery(first: $first, searchInput: $searchInput) { edges { id nimetus alias aadressid } } }"
        }
        r = requests.post(url, json=query, headers={'User-Agent': HEADERS['User-Agent'], 'Content-Type': 'application/json'}, timeout=10)
        edges = r.json().get('data', {}).get('jobOffersQuery', {}).get('edges', [])
        
        for job in edges:
            addrs = [str(a) for a in job.get('aadressid', []) if a]
            is_narva = any(
                ('narva' in a.lower() and 'narva mnt' not in a.lower() and 'tallinn' not in a.lower())
                for a in addrs
            )
            if not is_narva:
                continue
                
            job_id = str(job['id'])
            if job_id not in history.get('tootukassa', []):
                title = job['nimetus']
                print(f"  New Töötukassa: {title}")
                link = f"https://www.tootukassa.ee/et/toopakkumised/{job['alias']}"
                
                # Fetch full vacancy info
                full_info = fetch_tootukassa_details(job['id'], addrs)
                if not full_info:
                    full_info = f"Должность: {title}\nМесто работы: {', '.join(addrs)}"
                
                formatted_post = format_with_ai(title, full_info, "TÖÖTUKASSA", link, is_russian=False)
                if send_telegram(formatted_post, dry_run=dry_run):
                    new_ids.append(job_id)
                    sent_count += 1
                    time.sleep(2.5)
                    
                if sent_count >= max_posts:
                    break
    except Exception as e:
        print(f"  ❌ Error Töötukassa: {e}")
        
    if new_ids:
        history.setdefault('tootukassa', []).extend(new_ids)
        return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Narva Job Scraper Bot")
    parser.add_argument("--limit", type=int, default=1, help="Max new posts per source to send in this run (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Print posts without sending to Telegram")
    args = parser.parse_args()

    history = load_history()
    print(f"Starting Narva Job Scraper (limit per source: {args.limit}, dry_run: {args.dry_run})...")
    
    c1 = check_seti(history, max_posts=args.limit, dry_run=args.dry_run)
    c2 = check_cvkeskus(history, max_posts=args.limit, dry_run=args.dry_run)
    c3 = check_tootukassa(history, max_posts=args.limit, dry_run=args.dry_run)
    
    if (c1 or c2 or c3) and not args.dry_run:
        # Keep history list bounded to the latest 200 items per source
        for k in history:
            history[k] = history[k][-200:]
        save_history(history)
        print("\n✅ History updated in history.json.")
    else:
        print("\nℹ️ No new jobs sent or dry run mode.")
