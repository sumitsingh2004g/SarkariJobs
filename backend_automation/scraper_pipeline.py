import os
import json
import time
import random
import re
from datetime import date
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse

from curl_cffi import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError('SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set')
if not GEMINI_API_KEY:
    raise ValueError('GEMINI_API_KEY environment variables must be set')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

import google.genai as genai

MAX_DEPTH = 2
POLITE_DELAY_MIN = 2
POLITE_DELAY_MAX = 3

SPAM_PATTERNS = ['about', 'privacy', 'terms', 'contact', 'sitemap', 'rss', 'facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 'home']

def polite_delay():
    time.sleep(random.uniform(POLITE_DELAY_MIN, POLITE_DELAY_MAX))

def extract_clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav', 'aside', 'svg', 'img']):
        tag.decompose()
    
    content = soup.find(['article', 'main'])
    if not content:
        content = soup.find('div', class_=re.compile(r'(content|entry|post|article|main)', re.I))
    
    if content:
        text = content.get_text(separator='\n', strip=True)
    else:
        text = soup.get_text(separator='\n', strip=True)
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)

def is_valid_job_url(url: str, domain: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    for pattern in SPAM_PATTERNS:
        if re.search(r'/' + pattern + r'(?:/|$)', url_lower):
            return False
    return urlparse(url).netloc == urlparse(domain).netloc

def is_gov_official_url(url: str) -> bool:
    return bool(re.search(r'\.(gov\.in|nic\.in)/?$', url, re.I))

def scrape_freejobalert_deep() -> List[Dict[str, Any]]:
    jobs = []
    base_url = 'https://www.freejobalert.com/'
    
    try:
        resp = requests.get(base_url, impersonate="chrome", timeout=15)
        polite_delay()
        
        if resp.status_code != 200:
            return jobs
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        link_candidates = []
        
        for tr in soup.find_all('tr'):
            cells = tr.find_all(['td', 'th'])
            if len(cells) >= 2:
                cell_text = ' '.join(c.get_text(strip=True) for c in cells).lower()
                if any(k in cell_text for k in ['recruitment', 'vacancy', 'notification', 'apply', '2024', '2025', '2026', 'online']):
                    for a in tr.find_all('a', href=True):
                        href = a['href']
                        txt = a.get_text(strip=True)
                        if href and txt and len(txt) >= 25 and '/articles/' in href.lower():
                            full = href if href.startswith('http') else urljoin(base_url, href)
                            if is_valid_job_url(full, base_url):
                                link_candidates.append({'url': full, 'text': txt})
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            txt = a.get_text(strip=True)
            href_lower = href.lower() if href else ''
            if (href and txt and len(txt) >= 25 and 
                '/articles/' in href_lower and 
                is_valid_job_url(href, base_url) and
                'freejobalert' not in txt.lower()):
                full = href if href.startswith('http') else urljoin(base_url, href)
                link_candidates.append({'url': full, 'text': txt})
        
        seen = set()
        for lc in link_candidates[:15]:
            if lc['url'] not in seen:
                seen.add(lc['url'])
                try:
                    print(f"Crawling: {lc['url']}")
                    inner = requests.get(lc['url'], impersonate="chrome", timeout=15)
                    polite_delay()
                    if inner.status_code == 200:
                        inner_soup = BeautifulSoup(inner.text, 'html.parser')
                        clean_text = extract_clean_text(inner_soup)
                        if clean_text and len(clean_text) > 100:
                            jobs.append({
                                'title': lc['text'],
                                'link': lc['url'],
                                'content_for_gemini': clean_text[:4000]
                            })
                            if len(jobs) >= 20:
                                break
                except Exception as e:
                    print(f"Error: {e}")
                    
    except Exception as e:
        print(f"Error: {e}")
    
    return jobs

def scrape_sarkari_result_deep() -> List[Dict[str, Any]]:
    jobs = []
    base_url = 'https://www.sarkariresult.com/latestjob/'
    
    try:
        resp = requests.get(base_url, impersonate="chrome", timeout=15)
        polite_delay()
        
        if resp.status_code != 200:
            return jobs
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        link_candidates = []
        
        for tr in soup.find_all('tr'):
            for a in tr.find_all('a', href=True):
                href = a['href']
                txt = a.get_text(strip=True)
                href_lower = (href or '').lower()
                if href and txt and len(txt) >= 25:
                    if re.search(r'/(202[4-9]|upsssc|ups[cs]|rrb|ssc|bank|defence|nda|navy|army)/', href_lower):
                        full = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                        if is_valid_job_url(full, base_url):
                            link_candidates.append({'url': full, 'text': txt})
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            txt = a.get_text(strip=True)
            href_lower = (href or '').lower()
            if (href and txt and len(txt) >= 25 and
                re.search(r'/(202[4-9]|upsssc|ups[cs]|rrb|ssc|bank|defence|nda|navy|army)/', href_lower) and
                is_valid_job_url(href, base_url)):
                full = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                link_candidates.append({'url': full, 'text': txt})
        
        seen = set()
        for lc in link_candidates[:15]:
            if lc['url'] not in seen:
                seen.add(lc['url'])
                try:
                    print(f"Crawling: {lc['url']}")
                    inner = requests.get(lc['url'], impersonate="chrome", timeout=15)
                    polite_delay()
                    if inner.status_code == 200:
                        inner_soup = BeautifulSoup(inner.text, 'html.parser')
                        clean_text = extract_clean_text(inner_soup)
                        if clean_text and len(clean_text) > 100:
                            jobs.append({
                                'title': lc['text'],
                                'link': lc['url'],
                                'content_for_gemini': clean_text[:4000]
                            })
                            if len(jobs) >= 20:
                                break
                except Exception as e:
                    print(f"Error: {e}")
                    
    except Exception as e:
        print(f"Error: {e}")
    
    return jobs

def normalize_organization(text: str) -> str:
    mapping = {
        'SSC': ['ssc', 'staff selection'],
        'UPSC': ['upsc', 'union public service'],
        'Railways': ['railway', 'rpf', 'rrb'],
        'Banking': ['bank', 'ibps', 'sbi'],
        'Defence': ['defence', 'nda', 'cds', 'navy', 'army']
    }
    t = (text or '').lower()
    for org, keywords in mapping.items():
        if any(kw in t for kw in keywords):
            return org
    return 'Other'

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_jobs:
        return []
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    instruction = (
        "Extract structured data from Indian government job notices. Return valid JSON only.\n"
        "Fields to extract:\n"
        "1. title: The actual job/recruitment name (skip if generic site name)\n"
        "2. total_vacancies: Number from 'Total Vacancy', 'Total Posts', or table cells (sum category-wise if needed)\n"
        "3. apply_link: Official government URL ending in .gov.in or .nic.in\n"
        "4. start_date: Application start date (YYYY-MM-DD format or as written)\n"
        "5. last_date: Application deadline date (YYYY-MM-DD format or as written)\n"
        "6. application_fees: Fee amount or 'Not specified'\n"
        "7. eligibility: Required qualification or 'Not specified'\n"
    )
    
    results = []
    for job in raw_jobs:
        vac = 'Not specified'
        link = job.get('link', '')
        start = None
        last = '2026-12-31'
        fees = 'As per official notification'
        elig = 'Not specified'
        
        try:
            prompt = f"{instruction}\n\nText:\n{job.get('content_for_gemini', '')[:4000]}"
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            txt = response.text.strip()
            j = txt[txt.find('{'):txt.rfind('}')+1] if '{' in txt else '{}'
            data = json.loads(j)
            vac = data.get('total_vacancies', 'Not specified')
            link = data.get('apply_link', link)
            if data.get('start_date'):
                start = data.get('start_date')
            if data.get('last_date'):
                last = data.get('last_date')
            if data.get('application_fees'):
                fees = data.get('application_fees')
            if data.get('eligibility'):
                elig = data.get('eligibility')
        except Exception as e:
            print(f"Gemini error: {e}")
        
        results.append({
            'title': job.get('title', ''),
            'organization': normalize_organization(job.get('title', '')),
            'total_vacancies': vac,
            'start_date': start,
            'last_date': last,
            'fee_details': fees,
            'eligibility': elig,
            'official_apply_link': link
        })
    
    return results

def insert_job(job: Dict[str, Any]) -> bool:
    try:
        supabase.table('jobs').insert(job).execute()
        print(f"Inserted: {job.get('title')}")
        return True
    except Exception as e:
        print(f"Insert error: {e}")
        return False

def cleanup_expired():
    try:
        r = supabase.table('jobs').delete().lt('last_date', date.today().isoformat()).execute()
        print(f"Deleted {len(r.data or [])} expired")
    except Exception as e:
        print(f"Cleanup error: {e}")

def main():
    print('Starting Deep Crawler...')
    
    all_jobs = []
    all_jobs.extend(scrape_freejobalert_deep())
    all_jobs.extend(scrape_sarkari_result_deep())
    
    print(f"Total scraped: {len(all_jobs)}")
    
    if not all_jobs:
        all_jobs.append({
            'title': f'Test - {int(time.time())}',
            'organization': 'System',
            'total_vacancies': '1',
            'start_date': None,
            'last_date': '2026-12-31',
            'fee_details': 'Free',
            'eligibility': 'Test',
            'official_apply_link': 'https://example.com',
            'content_for_gemini': ''
        })
    
    processed = process_with_gemini(all_jobs)
    sum(1 for j in processed if insert_job(j))
    cleanup_expired()
    print('Done')

if __name__ == '__main__':
    main()