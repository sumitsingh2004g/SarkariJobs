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

import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)

MAX_DEPTH = 2
POLITE_DELAY_MIN = 2
POLITE_DELAY_MAX = 3

JOB_TITLE_MIN_LENGTH = 30
SPAM_KEYWORDS = ['home', 'about', 'privacy', 'terms', 'contact', 'sitemap', 'rss', 'facebook', 'twitter', 'instagram', 'linkedin', 'youtube']
SPAM_URL_PATTERNS = [r'/about', r'/privacy', r'/contact', r'/sitemap', r'/rss', r'/feed', r'\.pdf$', r'facebook', r'twitter', r'instagram', r'linkedin', r'youtube']

def polite_delay():
    delay = random.uniform(POLITE_DELAY_MIN, POLITE_DELAY_MAX)
    time.sleep(delay)

def is_spam_title(text: str) -> bool:
    if not text:
        return True
    t = text.strip().lower()
    if len(t) < JOB_TITLE_MIN_LENGTH and any(kw in t for kw in SPAM_KEYWORDS):
        return True
    if len(t) < 15:
        return True
    if 'freejobalert' in t and len(t) < 50:
        return True
    return False

def is_spam_url(url: str) -> bool:
    for pattern in SPAM_URL_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False

def extract_table_data(soup: BeautifulSoup) -> str:
    tables = soup.find_all('table')
    results = []
    for table in tables:
        rows = []
        for tr in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if cells:
                rows.append(' | '.join(cells))
        if rows:
            results.append('\n'.join(rows))
    return '\n\n'.join(results[-3:])

def extract_main_content(soup: BeautifulSoup) -> str:
    for tag in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav']):
        tag.decompose()
    
    main_divs = soup.find_all('div', class_=re.compile(r'(entry|content|article|post)', re.I))
    if main_divs:
        return ' '.join(d.get_text(separator=' ', strip=True)[:1500] for d in main_divs)
    
    paragraphs = []
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if len(text) > 50 and not any(x in text.lower() for x in SPAM_KEYWORDS):
            paragraphs.append(text)
    return '\n'.join(paragraphs[:10])

def crawl_deep(
    url: str,
    base_domain: str,
    current_depth: int,
    visited: set,
    title: str
) -> Optional[Dict[str, Any]]:
    if current_depth > MAX_DEPTH:
        return None
    
    if url in visited:
        return None
    
    visited.add(url)
    
    try:
        print(f"[Depth {current_depth}] {url}")
        resp = requests.get(url, impersonate="chrome", timeout=15)
        polite_delay()
        
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        content = extract_table_data(soup) + '\n' + extract_main_content(soup)
        
        if current_depth == MAX_DEPTH:
            return {'title': title, 'link': url, 'content_for_gemini': content[:4000]}
        
        candidate_links = []
        for tr in soup.find_all('tr'):
            cells = tr.find_all(['td', 'th'])
            if len(cells) >= 2:
                cell_text = ' '.join(c.get_text(strip=True) for c in cells).lower()
                if any(k in cell_text for k in ['notification', 'vacancy', 'recruitment', 'apply', '2024', '2025', '2026']):
                    for a in tr.find_all('a', href=True):
                        href = a['href']
                        txt = a.get_text(strip=True)
                        if href and txt and len(txt) >= JOB_TITLE_MIN_LENGTH and not is_spam_title(txt):
                            full = href if href.startswith('http') else urljoin(base_domain, href)
                            if not is_spam_url(full) and urlparse(full).netloc == urlparse(base_domain).netloc:
                                candidate_links.append({'url': full, 'text': txt})
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            txt = a.get_text(strip=True)
            if href and txt and len(txt) >= JOB_TITLE_MIN_LENGTH and not is_spam_title(txt) and not is_spam_url(href):
                full = href if href.startswith('http') else urljoin(base_domain, href)
                if urlparse(full).netloc == urlparse(base_domain).netloc and full not in visited:
                    candidate_links.append({'url': full, 'text': txt})
        
        seen = set()
        for link in candidate_links[:3]:
            if link['url'] not in seen:
                seen.add(link['url'])
                result = crawl_deep(link['url'], base_domain, current_depth + 1, visited.copy(), link['text'])
                if result:
                    return result
        
        return None
        
    except Exception as e:
        print(f"Error depth {current_depth}: {e}")
        return None

def scrape_freejobalert_deep() -> List[Dict[str, Any]]:
    jobs = []
    start_urls = ['https://www.freejobalert.com/']
    
    for base in start_urls:
        try:
            resp = requests.get(base, impersonate="chrome", timeout=15)
            polite_delay()
            
            if resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            link_candidates = []
            
            for tr in soup.find_all('tr'):
                cells = tr.find_all(['td', 'th'])
                if len(cells) >= 2:
                    cell_text = ' '.join(c.get_text(strip=True) for c in cells).lower()
                    if any(k in cell_text for k in ['recruitment', 'vacancy', 'notification', '2024', '2025', '2026']):
                        for a in tr.find_all('a', href=True):
                            href = a['href']
                            txt = a.get_text(strip=True)
                            if href and txt and len(txt) >= JOB_TITLE_MIN_LENGTH and not is_spam_title(txt):
                                full = href if href.startswith('http') else urljoin(base, href)
                                if not is_spam_url(full):
                                    link_candidates.append({'url': full, 'text': txt})
            
            seen = set()
            for lc in link_candidates[:12]:
                if lc['url'] not in seen:
                    seen.add(lc['url'])
                    result = crawl_deep(lc['url'], base, current_depth=1, visited=set(), title=lc['text'])
                    if result and result.get('content_for_gemini'):
                        jobs.append({
                            'title': result['title'],
                            'link': result['link'],
                            'content_for_gemini': result['content_for_gemini']
                        })
                        if len(jobs) >= 15:
                            break
            
            if jobs:
                break
                
        except Exception as e:
            print(f"Error: {e}")
    
    return jobs

def scrape_sarkari_result_deep() -> List[Dict[str, Any]]:
    jobs = []
    start_urls = ['https://www.sarkariresult.com/latestjob/']
    
    for base in start_urls:
        try:
            resp = requests.get(base, impersonate="chrome", timeout=15)
            polite_delay()
            
            if resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            link_candidates = []
            
            for tr in soup.find_all('tr'):
                for a in tr.find_all('a', href=True):
                    href = a['href']
                    txt = a.get_text(strip=True)
                    if href and txt and len(txt) >= JOB_TITLE_MIN_LENGTH and not is_spam_title(txt):
                        full = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                        if not is_spam_url(full):
                            link_candidates.append({'url': full, 'text': txt})
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                txt = a.get_text(strip=True)
                if href and txt and len(txt) >= JOB_TITLE_MIN_LENGTH and not is_spam_title(txt) and not is_spam_url(href):
                    full = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                    link_candidates.append({'url': full, 'text': txt})
            
            seen = set()
            for lc in link_candidates[:12]:
                if lc['url'] not in seen:
                    seen.add(lc['url'])
                    result = crawl_deep(lc['url'], base, current_depth=1, visited=set(), title=lc['text'])
                    if result and result.get('content_for_gemini'):
                        jobs.append({
                            'title': result['title'],
                            'link': result['link'],
                            'content_for_gemini': result['content_for_gemini']
                        })
                        if len(jobs) >= 15:
                            break
            
            if jobs:
                break
                
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
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    instruction = (
        "Extract from Indian govt job notices. JSON only.\n"
        "total_vacancies: From 'Total Vacancy', 'Total Posts', or table cells. Sum if needed.\n"
        "official_apply_link: Extract .gov.in/.nic.in URLs or 'Apply Online' links.\n"
        "Keys: total_vacancies (string), official_apply_link (string)."
    )
    
    results = []
    for job in raw_jobs:
        vac = 'Not specified'
        link = job.get('link', '')
        
        try:
            prompt = f"{instruction}\n\nTitle: {job.get('title', '')}\n\nContent:\n{job.get('content_for_gemini', '')[:4000]}"
            resp = model.generate_content(prompt)
            txt = resp.text.strip()
            j = txt[txt.find('{'):txt.rfind('}')+1] if '{' in txt else '{}'
            data = json.loads(j)
            vac = data.get('total_vacancies', 'Not specified')
            link = data.get('official_apply_link', link)
        except Exception as e:
            print(f"Gemini error: {e}")
        
        results.append({
            'title': job.get('title', ''),
            'organization': normalize_organization(job.get('title', '')),
            'total_vacancies': vac,
            'start_date': None,
            'last_date': '2026-12-31',
            'fee_details': 'As per official notification',
            'eligibility': 'Not specified',
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
    
    print(f"Total: {len(all_jobs)}")
    
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