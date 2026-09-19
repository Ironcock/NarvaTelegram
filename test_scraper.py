"""
Test script to verify job scraping from all 3 sources (Seti.ee, CVKeskus.ee, Tootukassa.ee)
without sending anything to Telegram or updating history.json.

Usage:
    python test_scraper.py
    python test_scraper.py --preview-ai   # Also tests AI translation on 1 sample job
"""

import os
import sys
import argparse
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Ensure UTF-8 output in Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv(Path(__file__).parent / ".env")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def test_seti(limit=5):
    print("\n" + "=" * 60)
    print(f"🔎 1. SETI.EE (Latest {limit} vacancies)")
    print("=" * 60)
    url = "https://www.magazin.seti.ee/modules/Board/index.php?pa=view&cid=33"
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.encoding = r.apparent_encoding or 'windows-1251'
        soup = BeautifulSoup(r.text, 'html.parser')
        links = soup.select('a[href*="viewannonces"]')
        print(f"Total board links found: {len(links)}")
        
        seen = set()
        count = 0
        for link in links:
            href = link.get('href')
            if not href.startswith('http'):
                href = "https://www.magazin.seti.ee/modules/Board/" + href
            if href in seen:
                continue
            seen.add(href)
            
            title = link.get_text(strip=True)
            if not title:
                continue
            
            count += 1
            # Fetch ad details
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
                    desc_text = d_soup.get_text(separator=" ", strip=True)[:300]
            except Exception as ex:
                desc_text = f"Error: {ex}"
                
            snippet = " ".join(desc_text.split())[:160]
            print(f"\n[{count}] {title}")
            print(f"    🔗 URL: {href}")
            print(f"    📝 Text: {snippet}...")
            
            results.append({"title": title, "url": href, "desc": desc_text, "source": "Seti.ee"})
            if count >= limit:
                break
                
    except Exception as e:
        print(f"❌ Error scraping Seti.ee: {e}")
    return results

def test_cvkeskus(limit=5):
    print("\n" + "=" * 60)
    print(f"🔎 2. CVKESKUS.EE (Latest {limit} jobs in Ida-Virumaa / Narva)")
    print("=" * 60)
    url = "https://www.cvkeskus.ee/toopakkumised?op=search&search%5Blocations%5D%5B%5D=6&sort=activation_date"
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, 'html.parser')
        jobs = soup.select('a.jobad-url')
        print(f"Total job elements found: {len(jobs)}")
        
        seen = set()
        count = 0
        for job in jobs:
            href = job.get('href')
            if not href.startswith('http'):
                href = 'https://www.cvkeskus.ee' + href
            if href in seen:
                continue
            seen.add(href)
            
            title_tag = job.find('h2')
            title = title_tag.text.strip() if title_tag else job.get_text(strip=True)
            if not title:
                continue
                
            count += 1
            desc_text = ""
            try:
                d_r = requests.get(href, headers=HEADERS, timeout=10)
                d_soup = BeautifulSoup(d_r.content, 'html.parser')
                desc = d_soup.select_one('.job-offer')
                desc_text = desc.get_text(separator=" ", strip=True) if desc else d_soup.get_text(separator=" ", strip=True)[:400]
            except Exception as ex:
                desc_text = f"Error: {ex}"
                
            snippet = " ".join(desc_text.split())[:160]
            print(f"\n[{count}] {title}")
            print(f"    🔗 URL: {href}")
            print(f"    📝 Text: {snippet}...")
            
            results.append({"title": title, "url": href, "desc": desc_text, "source": "CVKeskus"})
            if count >= limit:
                break
                
    except Exception as e:
        print(f"❌ Error scraping CVKeskus.ee: {e}")
    return results

def test_tootukassa(limit=5):
    print("\n" + "=" * 60)
    print(f"🔎 3. TOOTUKASSA.EE (Latest {limit} jobs matching Narva)")
    print("=" * 60)
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
    results = []
    try:
        r = requests.post(url, json=query, headers={'User-Agent': HEADERS['User-Agent'], 'Content-Type': 'application/json'}, timeout=10)
        data = r.json()
        edges = data.get('data', {}).get('jobOffersQuery', {}).get('edges', [])
        print(f"Offers returned from GraphQL query: {len(edges)}")
        
        count = 0
        for job in edges:
            addrs = [str(a) for a in job.get('aadressid', []) if a]
            is_narva = any(
                ('narva' in a.lower() and 'narva mnt' not in a.lower() and 'tallinn' not in a.lower())
                for a in addrs
            )
            if not is_narva:
                continue
                
            count += 1
            title = job.get('nimetus', 'N/A')
            alias = job.get('alias', '')
            job_url = f"https://www.tootukassa.ee/et/toopakkumised/{alias}"
            
            print(f"\n[{count}] {title}")
            print(f"    📍 Address: {', '.join(addrs)}")
            print(f"    🔗 URL: {job_url}")
            
            results.append({"title": title, "url": job_url, "desc": f"Asukoht: {', '.join(addrs)}", "source": "Töötukassa"})
            if count >= limit:
                break
                
    except Exception as e:
        print(f"❌ Error querying Tootukassa GraphQL: {e}")
    return results

def preview_ai(sample_job):
    print("\n" + "=" * 60)
    print("🤖 AI TRANSLATION & FORMATTING PREVIEW")
    print("=" * 60)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("⚠️ GEMINI_API_KEY not found in .env")
        return

    import google.generativeai as genai
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-3.6-flash')
    
    prompt = f"""
You format job postings for a Russian-speaking Telegram channel in Narva, Estonia.
Given this vacancy from {sample_job['source']}:
Title: {sample_job['title']}
Content: {sample_job['desc'][:2000]}

Format it cleanly for Telegram in Russian HTML mode:
- <b>Bold Title</b> in Russian
- Key details (Company, duties, requirements, conditions, salary) with emojis
- Concise, clear, easy to read on mobile.
- Use ONLY <b>, <i>, <code> tags. No markdown (**), no ```html blocks.
"""
    try:
        response = model.generate_content(prompt)
        print(f"Sample source: {sample_job['source']} - {sample_job['title']}")
        print(f"Sample link: {sample_job['url']}")
        print("-" * 40)
        print(response.text.strip())
        print("-" * 40)
    except Exception as e:
        print(f"AI generation error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test job scrapers for Narva Telegram bot.")
    parser.add_argument("--preview-ai", action="store_true", help="Generate AI preview for 1 vacancy")
    args = parser.parse_args()

    s1 = test_seti(5)
    s2 = test_cvkeskus(5)
    s3 = test_tootukassa(5)

    print("\n" + "=" * 60)
    print(f"✅ Scraping test complete! Got {len(s1)} Seti, {len(s2)} CVKeskus, {len(s3)} Töötukassa.")
    print("=" * 60)

    if args.preview_ai:
        sample = s2[0] if s2 else (s3[0] if s3 else (s1[0] if s1 else None))
        if sample:
            preview_ai(sample)
