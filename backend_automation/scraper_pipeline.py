import os
import json
import re
import time
import urllib3
from datetime import date
from typing import List, Dict, Any

import requests
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

from bs4 import BeautifulSoup
from supabase import create_client, Client
import google.generativeai as genai

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "DNT": "1"
}

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError('SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set')

if not GEMINI_API_KEY:
    raise ValueError('GEMINI_API_KEY environment variable must be set')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ORGANIZATION_MAPPING = {
    'SSC': ['ssc', 'staff selection commission'],
    'UPSC': ['upsc', 'union public service commission'],
    'Railways': ['railway', 'rpf', 'rrb'],
    'Banking': ['bank', 'ibps', 'sbi', 'po'],
    'Defence': ['defence', 'nda', 'cds', 'navy', 'army']
}

def create_scraper():
    if CLOUDSCRAPER_AVAILABLE:
        scraper = cloudscraper.create_scraper()
        scraper.headers.update(HEADERS)
        return scraper
    return requests.Session()

def normalize_organization(text: str) -> str:
    if not text:
        return 'Other'
    text_lower = text.lower()
    for org, keywords in ORGANIZATION_MAPPING.items():
        for keyword in keywords:
            if keyword in text_lower:
                return org
    return 'Other'

def scrape_sarkari_result() -> List[Dict[str, Any]]:
    jobs = []
    scraper = create_scraper()
    
    rss_urls = [
        'https://www.sarkariresult.com/rss.php',
        'https://sarkariresult.com/feed',
    ]
    
    for rss_url in rss_urls:
        try:
            if CLOUDSCRAPER_AVAILABLE:
                response = scraper.get(rss_url, timeout=15)
            else:
                response = requests.get(rss_url, headers=HEADERS, timeout=15)
            
            print(f'sarkariresult RSS ({rss_url}): Status {response.status_code}')
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'xml')
                
                for item in soup.find_all('item'):
                    title_tag = item.find('title')
                    link_tag = item.find('link')
                    title = title_tag.get_text(strip=True) if title_tag else ''
                    link = link_tag.get_text(strip=True) if link_tag else ''
                    
                    if title and len(title) >= 10:
                        jobs.append({
                            'title': title,
                            'raw_content': f'Title: {title}\nLink: {link}',
                            'link': link or rss_url
                        })
                
                print(f'sarkariresult RSS: Found {len(jobs)} items via BeautifulSoup XML parser')
                if jobs:
                    return jobs[:20]
        except Exception as e:
            print(f'sarkariresult RSS error: {type(e).__name__}: {e}')
        time.sleep(2)
    
    return jobs[:20]

def scrape_freejobalert() -> List[Dict[str, Any]]:
    jobs = []
    scraper = create_scraper()
    
    urls = ['https://www.freejobalert.com/', 'https://freejobalert.com/']
    
    for url in urls:
        try:
            if CLOUDSCRAPER_AVAILABLE:
                response = scraper.get(url, timeout=15)
            else:
                response = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            
            print(f'freejobalert ({url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL)
            tr_matches = tr_pattern.findall(response.text)
            
            for tr_match in tr_matches:
                if any(k in tr_match.lower() for k in ['recruitment', 'vacancy', 'notification', '2024', '2025', '2026', 'apply']):
                    a_pattern = re.compile(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
                    a_matches = a_pattern.findall(tr_match)
                    for href, title in a_matches[:2]:
                        title_clean = title.strip()
                        if len(title_clean) >= 10:
                            href_clean = href.strip()
                            full_url = href_clean if href_clean.startswith('http') else f'https://freejobalert.com{href_clean}'
                            jobs.append({
                                'title': title_clean,
                                'raw_content': f'Title: {title_clean}\nLink: {full_url}',
                                'link': full_url
                            })
            
            print(f'freejobalert: Found {len(jobs)} listings via regex')
            if jobs:
                return jobs[:20]
        except Exception as e:
            print(f'freejobalert ({url}) error: {type(e).__name__}: {e}')
        time.sleep(2)
    
    return jobs[:20]

def scrape_sarkari_exams() -> List[Dict[str, Any]]:
    jobs = []
    scraper = create_scraper()
    
    urls = ['https://www.sarkariexams.com/', 'https://sarkariexams.com/']
    
    for url in urls:
        try:
            if CLOUDSCRAPER_AVAILABLE:
                response = scraper.get(url, timeout=15)
            else:
                response = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            
            print(f'sarkariexams ({url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            h_pattern = re.compile(r'<(h2|h3|h4)[^>]*>(.*?)</\1>', re.IGNORECASE | re.DOTALL)
            h_matches = h_pattern.findall(response.text)
            
            for tag, text in h_matches:
                text_clean = text.strip()
                if len(text_clean) >= 15 and any(k in text_clean.lower() for k in ['recruitment', 'vacancy', '2024', '2025', '2026', 'exam', 'notification']):
                    jobs.append({
                        'title': text_clean,
                        'raw_content': f'Title: {text_clean}\nLink: {url}',
                        'link': url
                    })
            
            print(f'sarkariexams: Found {len(jobs)} listings via regex')
            if jobs:
                return jobs[:15]
        except Exception as e:
            print(f'sarkariexams ({url}) error: {type(e).__name__}: {e}')
        time.sleep(2)
    
    return jobs[:15]

def scrape_indeed_govt() -> List[Dict[str, Any]]:
    jobs = []
    scraper = create_scraper()
    
    url = 'https://in.indeed.com/jobs?q=government+jobs&jt=fulltime'
    
    try:
        if CLOUDSCRAPER_AVAILABLE:
            response = scraper.get(url, timeout=15)
        else:
            response = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        
        print(f'indeed govt ({url}): Status {response.status_code}')
        
        if response.status_code == 200:
            tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL)
            tr_matches = tr_pattern.findall(response.text)
            
            for tr_match in tr_matches:
                if any(k in tr_match.lower() for k in ['government', 'recruitment', 'vacancy']):
                    a_pattern = re.compile(r'<a[^>]*href=["\'](/viewjob[^"\']*)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
                    a_matches = a_pattern.findall(tr_match)
                    for href, title in a_matches[:2]:
                        title_clean = title.strip()
                        if len(title_clean) >= 10:
                            jobs.append({
                                'title': title_clean,
                                'raw_content': f'Title: {title_clean}\nLink: https://in.indeed.com{href}',
                                'link': f'https://in.indeed.com{href}'
                            })
            
            print(f'indeed govt: Found {len(jobs)} listings')
            return jobs[:15]
    except Exception as e:
        print(f'indeed govt error: {type(e).__name__}: {e}')
    
    return jobs[:15]

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_jobs:
        return []
    
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    processed_jobs = []
    
    for job in raw_jobs:
        prompt = f"""Extract job details. Look for "Date", "Last Date", "Post Name", "Link".

Return ONLY valid JSON:
{{
  "title": "cleaned job title max 100 chars",
  "total_vacancies": "string like '100+' or 'Not specified'",
  "start_date": "YYYY-MM-DD or null",
  "last_date": "YYYY-MM-DD mandatory - use far future date if unknown",
  "fee_details": "application fees or 'As per official notification'",
  "eligibility": "age and education requirements",
  "official_apply_link": "URL"
}}

Source: {job['raw_content']}"""
        
        try:
            response = model.generate_content(prompt)
            json_text = response.text.strip()
            
            if json_text.startswith('```'):
                json_text = '\n'.join(json_text.split('\n')[1:-1]).strip()
            
            parsed = json.loads(json_text)
            org = normalize_organization(parsed.get('title', ''))
            parsed['organization'] = org
            
            if not parsed.get('last_date'):
                parsed['last_date'] = '2026-12-31'
            if not parsed.get('official_apply_link') and job.get('link'):
                parsed['official_apply_link'] = job['link']
            
            processed_jobs.append(parsed)
            print(f'Processed: {parsed.get("title", "Unknown")}')
            
        except json.JSONDecodeError as e:
            print(f'JSON decode error for {job.get("title", "Unknown")}: {e}')
        except Exception as e:
            print(f'Gemini error: {type(e).__name__}: {e}')
        
        time.sleep(1)
    
    return processed_jobs

def insert_job(job: Dict[str, Any]) -> bool:
    try:
        existing = supabase.table('jobs').select('id').eq('title', job.get('title', '')).eq('organization', job.get('organization', '')).execute()
        
        if existing.data and len(existing.data) > 0:
            print(f'Skip existing: {job.get("title")}')
            return False
        
        job_data = {
            'title': job.get('title', ''),
            'organization': job.get('organization', 'Other'),
            'total_vacancies': job.get('total_vacancies', 'Not specified'),
            'start_date': job.get('start_date'),
            'last_date': job.get('last_date') or '2026-12-31',
            'fee_details': job.get('fee_details', 'As per official notification'),
            'eligibility': job.get('eligibility', 'Not specified'),
            'official_apply_link': job.get('official_apply_link', '')
        }
        
        result = supabase.table('jobs').insert(job_data).execute()
        
        if result.data:
            print(f'Inserted: {job.get("title")}')
            return True
        return False
            
    except Exception as e:
        print(f'Insert error for {job.get("title", "Unknown")}: {type(e).__name__}: {e}')
        return False

def cleanup_expired_jobs() -> int:
    today = date.today().isoformat()
    
    try:
        result = supabase.table('jobs').delete().lt('last_date', today).execute()
        count = len(result.data) if result.data else 0
        print(f'Deleted {count} expired jobs')
        return count
    except Exception as e:
        print(f'Cleanup error: {type(e).__name__}: {e}')
        return 0

def main():
    print('Starting Sarkari Jobs pipeline...')
    
    all_jobs = []
    all_jobs.extend(scrape_sarkari_result())
    time.sleep(2)
    all_jobs.extend(scrape_freejobalert())
    time.sleep(2)
    all_jobs.extend(scrape_sarkari_exams())
    time.sleep(2)
    all_jobs.extend(scrape_indeed_govt())
    
    total_scraped = len(all_jobs)
    print(f'Total scraped: {total_scraped} listings')
    
    if total_scraped == 0:
        print('No jobs scraped - adding test connection job')
        all_jobs.append({
            'title': 'Test Connection Job',
            'organization': 'System Test',
            'total_vacancies': '1',
            'start_date': None,
            'last_date': '2026-12-31',
            'fee_details': 'Free',
            'eligibility': 'Test',
            'official_apply_link': 'https://example.com'
        })
        processed_jobs = all_jobs
    else:
        processed_jobs = process_with_gemini(all_jobs)
    
    if not processed_jobs:
        print('No jobs processed - exiting')
        return
    
    inserted_count = sum(1 for job in processed_jobs if insert_job(job))
    deleted_count = cleanup_expired_jobs()
    
    print(f'Pipeline complete. Inserted: {inserted_count}, Deleted expired: {deleted_count}')

if __name__ == '__main__':
    main()