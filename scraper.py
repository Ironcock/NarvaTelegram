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

# Ensure UTF-8 output and instant line buffering
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HISTORY_FILE = Path(__file__).parent / "history.json"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Validation
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ ERROR: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is missing! Please set them in .env or GitHub Secrets.")
    sys.exit(1)

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

# Approximate road distances from Narva (km) for Estonian settlements
ESTONIA_DISTANCES_FROM_NARVA = {
    'narva-jõesuu': 15, 'narva joesuu': 15, 'нарва-йыэсуу': 15, 'нарва йыэсуу': 15, 'sinimäe': 18,
    'sillamäe': 25, 'силламяэ': 25,
    'jõhvi': 50, 'johvi': 50, 'йыхви': 50,
    'kohtla-järve': 55, 'kohtla jarve': 55, 'кохтла-ярве': 55, 'ahtme': 50, 'ахтме': 50,
    'toila': 45, 'тойла': 45,
    'kiviõli': 75, 'kivioli': 75, 'кивиыли': 75,
    'püssi': 70, 'пюсси': 70,
    'iisaku': 65, 'ийсаку': 65,
    'rakvere': 115, 'раквере': 115,
    'kunda': 105, 'кунда': 105,
    'tapa': 145, 'тапа': 145,
    'raasiku': 190, 'raaziku': 190, 'раазику': 190,
    'tallinn': 210, 'таллинн': 210, 'таллин': 210,
    'maardu': 195, 'маарду': 195,
    'viimsi': 210, 'виймси': 210,
    'jüri': 200, 'юри': 200,
    'saue': 230, 'сауэ': 230,
    'keila': 235, 'кейла': 235,
    'paldiski': 255, 'палдиски': 255,
    'tartu': 180, 'тарту': 180,
    'mustvee': 115, 'муствеэ': 115,
    'kallaste': 135, 'калласте': 135,
    'jõgeva': 150, 'йыгева': 150,
    'viljandi': 235, 'вильянди': 235,
    'pärnu': 290, 'parnu': 290, 'пярну': 290,
    'paide': 180, 'пайде': 180,
    'türi': 190, 'тюри': 190,
    'valga': 265, 'валга': 265,
    'võru': 245, 'выру': 245,
    'haapsalu': 305, 'хаапсалу': 305,
    'kuressaare': 425, 'курессааре': 425,
}

def get_distance_annotation(location_text):
    if not location_text:
        return ''
    loc_lower = location_text.lower()
    # If explicitly in Narva (and not Narva-Jõesuu), no distance needed
    if 'narva' in loc_lower or 'нарва' in loc_lower:
        if not any(k in loc_lower for k in ['narva-jõesuu', 'narva joesuu', 'нарва-йыэсуу', 'нарва йыэсуу']):
            return ''
    for city, dist in ESTONIA_DISTANCES_FROM_NARVA.items():
        if city in loc_lower:
            return f' (~{dist} км от Нарвы)'
    return ''

def format_with_ai(title, content, source_name, url, is_russian=False):
    task_desc = "Отредактируй и оформи это объявление" if is_russian else "Переведи на русский язык и оформи вакансию"
    prompt = f"""
Ты — честный и предельно точный редактор Telegram-канала с вакансиями в Эстонии.
Канал ведется специально для соискательницы по имени Оксана (тел. +372 5833 5039).
Оксана имеет многолетний практический опыт работы на производстве и складах (производственные процессы, контроль качества, приёмка продукции, ведение отчётности, аккуратность, ответственность, готовность сразу приступить к работе). Также при её трудоустройстве работодатель может оформить субсидию на зарплату (palgatoetus) от Töötukassa.

ТВОЯ ЗАДАЧА:
1. {task_desc} в аккуратный, лаконичный и удобный для чтения с телефона Telegram-пост.
2. В конце поста добавь персональный шаблон письма для отклика от имени Оксаны, адаптированный под эту вакансию, внутри скрытого сворачиваемого блока blockquote.

Вакансия: {title}
Источник: {source_name}
Ссылка: {url}
Данные из первоисточника:
{content}

КАТЕГОРИЧЕСКИЕ ПРАВИЛА (СТРОГО БЕЗ ВЫДУМЫВАНИЯ В ОПИСАНИИ ВАКАНСИИ):
1. ИСПОЛЬЗУЙ ТОЛЬКО ТУ ИНФОРМАЦИЮ, КОТОРАЯ ПРЯМО НАПИСАНА В ТЕКСТЕ ДАННЫХ ВЫШЕ.
2. СТРОГО ЗАПРЕЩЕНО ВЫДУМЫВАТЬ ИЛИ ДОБАВЛЯТЬ ЛЮБЫЕ НЕСУЩЕСТВУЮЩИЕ ДЕТАЛИ:
   - Если в тексте НЕТ списка обязанностей — НЕ ВЫДУМЫВАЙ ИХ! НЕ ДОБАВЛЯЙ РАЗДЕЛ "Обязанности"!
   - Если в тексте НЕТ требований к кандидату — НЕ ВЫДУМЫВАЙ ИХ! НЕ ДОБАВЛЯЙ РАЗДЕЛ "Требования"!
   - Если в тексте НЕТ образования — НЕ ВЫДУМЫВАЙ образование! ПРОПУСТИ эту строку.
   - Если в тексте НЕТ требований к языкам — НЕ ПИШИ пункт про языки! ПРОПУСТИ эту строку.
   - Если в тексте НЕТ названия компании / работодателя — НЕ ПИШИ выдуманное название! ПРОПУСТИ строку работодателя.
   - Если в тексте НЕТ точного адреса улицы — укажи только указанный город или место.
   - Если в тексте НЕТ графика/смен — не пиши "полная занятость" наугад.
   - Если объявление короткое (всего пара предложений) — пост ДОЛЖЕН быть коротким! Пиши ТОЛЬКО то, что реально есть в объявлении.

ПРАВИЛА ОФОРМЛЕНИЯ ПОСТА:
- Первая строка: <b>Название должности</b> (из названия вакансии)
- 🏢 <b>Работодатель:</b> (ТОЛЬКО если названа конкретная фирма/организация. Если нет — пропусти строку полностью).
- 📍 <b>Место работы / Адрес:</b> (город/место, указанные в тексте. Если в тексте указано расстояние от Нарвы или если место вне Нарвы, обязательно сохрани расстояние в скобках, например: <code>пос. Раазику (~190 км от Нарвы)</code> или <code>г. Силламяэ (~25 км от Нарвы)</code>. Если работа в Нарве — расстояние указывать не нужно).
- 💰 <b>Зарплата:</b> (укажи сумму и условия ТОЧНО как в тексте. Если не указана — напиши: <i>По договоренности / не указана</i>)
- ⏳ <b>Срок подачи заявки:</b> (ТОЛЬКО если указана дата окончания или дедлайн)
- ⏱️ <b>График / Занятость:</b> (ТОЛЬКО если прямо упомянуты в данных: смены, полная/частичная занятость, дата старта)
- 🗣️ <b>Языки:</b> (ТОЛЬКО если в тексте есть конкретные требования к языкам. Иначе пропусти строку полностью).
- 🎓 <b>Образование / Компьютер:</b> (ТОЛЬКО если указаны в данных. Иначе пропусти строку полностью).
- 📋 <b>Обязанности:</b> (ТОЛЬКО если в данных есть реальный перечень обязанностей. Иначе пропусти).
- 🎯 <b>Требования:</b> (ТОЛЬКО если в данных есть реальные требования. Иначе пропусти).
- 💼 <b>Условия работодателя:</b> (ТОЛЬКО если в данных упомянуты условия: жилье, официальное трудоустройство, отпуск и т.п.).
- 📞 <b>Контакты:</b> 
    - Телефоны: ОБЯЗАТЕЛЬНО строго в формате <code>+372XXXXXXXX</code> целиком, без пробелов внутри.
    - Имя контактного лица (если указано).
    - Email (если указан).

- Шаблон письма для отклика — ОБЯЗАТЕЛЬНО оформи строго в следующем виде:
<blockquote expandable>📩 <b>Шаблон письма:</b>
<code>
[Здесь составь текст письма от имени Оксаны, адаптированный под эту вакансию:
- Приветствие: по имени контактного лица, если известно (например: "Здравствуйте, Владислав!" или "Здравствуйте, Наталья!"), иначе просто "Здравствуйте!".
- Указание должности и компании/завода, если названы.
- Опыт работы на производстве/складах, аккуратность, готовность сразу приступить к работе.
- ОБЯЗАТЕЛЬНО предложение субсидии: "Также при моём трудоустройстве возможно оформление субсидии на выплату заработной платы (palgatoetus) от Töötukassa."
- Упоминание прикрепленного резюме и готовности к собеседованию.
- Подпись:
С уважением,
Оксана
+372 5833 5039]
</code>
</blockquote>

- В самом конце:
    🔗 <b>Источник:</b> <a href="{url}">{source_name}</a>

ФОРМАТИРОВАНИЕ И ОГРАНИЧЕНИЯ:
- НИКАКИХ ХЕШТЕГОВ (хештеги запрещены!).
- Используй ТОЛЬКО Telegram HTML теги: <b>, <i>, <code>, <a>, <blockquote>, <pre>. Никакого Markdown (** или ##), никаких кодовых блоков.
"""
    for model_name in ['gemini-3.6-flash', 'gemini-flash-latest', 'gemini-3.5-flash-lite', 'gemini-3.5-flash']:
        try:
            m = genai.GenerativeModel(model_name)
            resp = m.generate_content(prompt, request_options={'timeout': 25})
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
                
                dist_ann = get_distance_annotation(desc_text)
                if dist_ann and "от Нарвы" not in desc_text:
                    desc_text += f"\nПримерное расстояние: {dist_ann}"

                formatted_post = format_with_ai(title, desc_text, "SETI.EE", href, is_russian=True)
                if send_telegram(formatted_post, dry_run=dry_run):
                    new_ids.append(job_id)
                    sent_count += 1
                    time.sleep(6)
                
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
                    time.sleep(6)
                    
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
        if addresses:
            addr_str = ', '.join(addresses)
            dist_ann = get_distance_annotation(addr_str)
            summary.append(f"Точный адрес / Место работы: {addr_str}{dist_ann}")
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
                    time.sleep(6)
                    
                if sent_count >= max_posts:
                    break
    except Exception as e:
        print(f"  ❌ Error Töötukassa: {e}")
        
    if new_ids:
        history.setdefault('tootukassa', []).extend(new_ids)
        return True
    return False


def init_baseline_history():
    """Fetches all currently visible IDs across Seti, CVKeskus, and Tootukassa and saves them to history.json without sending anything to Telegram."""
    print("🔄 Initializing baseline history from all 3 portals...")
    history = {"seti": [], "cvkeskus": [], "tootukassa": []}
    
    # 1. Seti.ee
    try:
        r = requests.get("https://www.magazin.seti.ee/modules/Board/index.php?pa=view&cid=33", headers=HEADERS, timeout=10)
        r.encoding = r.apparent_encoding or 'windows-1251'
        soup = BeautifulSoup(r.text, 'html.parser')
        for link in soup.select('a[href*="viewannonces"]'):
            href = link.get('href')
            if not href.startswith('http'):
                href = "https://www.magazin.seti.ee/modules/Board/" + href
            if href not in history["seti"]:
                history["seti"].append(href)
        print(f"  ✅ Seti.ee: found {len(history['seti'])} active ads.")
    except Exception as e:
        print(f"  ❌ Error fetching Seti ads: {e}")

    # 2. CVKeskus.ee
    try:
        r = requests.get("https://www.cvkeskus.ee/toopakkumised?op=search&search%5Blocations%5D%5B%5D=6&sort=activation_date", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, 'html.parser')
        for job in soup.select('a.jobad-url'):
            href = job.get('href', '')
            job_id = href.split('-')[-1]
            if job_id and job_id not in history["cvkeskus"]:
                history["cvkeskus"].append(job_id)
        print(f"  ✅ CVKeskus.ee: found {len(history['cvkeskus'])} active ads.")
    except Exception as e:
        print(f"  ❌ Error fetching CVKeskus ads: {e}")

    # 3. Tootukassa.ee
    try:
        url = "https://www.tootukassa.ee/web/graphql"
        query = {
            "operationName": "jobOfferSearch",
            "variables": {"first": 50, "searchInput": {"otsisona": "Narva"}},
            "query": "query jobOfferSearch($first: Int, $searchInput: InputToopakkumineAvalikOtsingDTO) { jobOffersQuery(first: $first, searchInput: $searchInput) { edges { id aadressid } } }"
        }
        r = requests.post(url, json=query, headers={'User-Agent': HEADERS['User-Agent'], 'Content-Type': 'application/json'}, timeout=10)
        edges = r.json().get('data', {}).get('jobOffersQuery', {}).get('edges', [])
        for job in edges:
            addrs = [str(a) for a in job.get('aadressid', []) if a]
            is_narva = any(('narva' in a.lower() and 'narva mnt' not in a.lower() and 'tallinn' not in a.lower()) for a in addrs)
            if is_narva:
                job_id = str(job['id'])
                if job_id not in history["tootukassa"]:
                    history["tootukassa"].append(job_id)
        print(f"  ✅ Töötukassa.ee: found {len(history['tootukassa'])} active Narva jobs.")
    except Exception as e:
        print(f"  ❌ Error fetching Tootukassa jobs: {e}")

    # Prune each list to latest 200 just in case
    for k in history:
        history[k] = history[k][-200:]
        
    save_history(history)
    total = sum(len(v) for v in history.values())
    print(f"\n🎉 Baseline initialized! Total {total} active vacancies recorded into history.json.")
    print("Future scraper runs will only post vacancies published AFTER this moment.")
    return history


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Narva Job Scraper Bot")
    parser.add_argument("--limit", type=int, default=10, help="Max new posts per source to send in this run (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Print posts without sending to Telegram")
    parser.add_argument("--init-history", action="store_true", help="Seed history.json with all current active jobs as baseline without sending to Telegram")
    args = parser.parse_args()

    if args.init_history:
        init_baseline_history()
        sys.exit(0)

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
