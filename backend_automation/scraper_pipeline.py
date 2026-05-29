import os
import json
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
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.google.com/",
    "Accept-Encoding": "gzip, deflate, br"
}

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError('SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set')

if not GEMINI_API_KEY:
    raise ValueError('GEMINI_API_KEY environment variable must be set')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ORGANIZATION_MAPPING = {
    'SSC': ['ssc', 'staff selection commission'],
    'UPSC': ['upsc', 'union public service commission'],
    'Railways': ['railway', 'rpf', 'rrb', 'railways'],
    'Banking': ['bank', 'ibps', 'sbi', 'po'],
    'Defence': ['defence', 'nda', 'cds', 'navy', 'army', 'air force']
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
    
    urls_to_try = [
        'https://www.sarkariresult.com/',
        'https://sarkariresult.com/',
    ]
    
    for url in urls_to_try:
        try:
            if CLOUDSCRAPER_AVAILABLE:
                response = scraper.get(url, timeout=15)
            else:
                response = requests.get(url, headers=HEADERS, timeout=15)
            
            print(f'sarkariresult.com ({url}): Status {response.status_code}')
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for div in soup.find_all(['div', 'li', 'td', 'p']):
                link = div.find('a', href=True)
                if link:
                    title = link.get_text(strip=True)
                    href = link['href']
                    if title and len(title) >= 10:
                        keywords = ['recruitment', 'vacancy', 'notification', 'exam', 'online', 'apply']
                        if any(k in title.lower() or k in div.get_text(strip=True).lower() for k in keywords):
                            full_url = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                            jobs.append({
                                'title': title,
                                'raw_content': f'Title: {title}\nLink: {full_url}',
                                'link': full_url
                            })
            print(f'sarkariresult.com ({url}): Found {len(jobs)} listings')
            if jobs:
                return jobs[:10]
        except Exception as e:
            print(f'sarkariresult.com ({url}) error: {type(e).__name__}: {e}')
        time.sleep(2)
    
    return jobs[:10]

def scrape_sarkari_exams() -> List[Dict[str, Any]]:
    jobs = []
    scraper = create_scraper()
    
    urls_to_try = [
        'https://www.sarkariexams.com/',
        'https://sarkariexams.com/',
    ]
    
    for url in urls_to_try:
        try:
            if CLOUDSCRAPER_AVAILABLE:
                response = scraper.get(url, timeout=15)
            else:
                response = requests.get(url, headers=HEADERS, timeout=15, verify=False)
            
            print(f'sarkariexams.com ({url}): Status {response.status_code}')
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for item in soup.find_all(['h2', 'h3', 'div', 'li', 'p']):
                text = item.get_text(strip=True)
                link = item.find('a', href=True)
                href = link['href'] if link else ''
                
                if text and len(text) >= 15:
                    keywords = ['recruitment', 'vacancy', 'exam', '2024', '2025', '2026', 'apply', 'notification']
                    if any(k in text.lower() for k in keywords):
                        jobs.append({
                            'title': text,
                            'raw_content': f'Title: {text}\nLink: {href}',
                            'link': href
                        })
            print(f'sarkariexams.com ({url}): Found {len(jobs)} listings')
            if jobs:
                return jobs[:10]
        except Exception as e:
            print(f'sarkariexams.com ({url}) error: {type(e).__name__}: {e}')
        time.sleep(2)
    
    return jobs[:10]

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    processed_jobs = []
    
    for job in raw_jobs:
        prompt = f"""Extract job details as valid JSON only (no markdown):

Input: {job['raw_content']}

Output format:
{{
  "title": "cleaned job title max 100 chars",
  "total_vacancies": "string like '100+' or 'Not specified'",
  "start_date": "YYYY-MM-DD or null",
  "last_date": "YYYY-MM-DD mandatory",
  "fee_details": "application fees or 'As per official notification'",
  "eligibility": "age and education requirements",
  "official_apply_link": "URL"
}}"""
        
        try:
            response = model.generate_content(prompt)
            json_text = response.text.strip()
            
            if json_text.startswith('```'):
                json_text = '\n'.join(json_text.split('\n')[1:-1])
            
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
            print(f'Gemini processing error: {type(e).__name__}: {e}')
        
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
    
    all_jobs = scrape_sarkari_result()
    time.sleep(2)
    all_jobs += scrape_sarkari_exams()
    
    print(f'Total scraped: {len(all_jobs)} listings')
    
    if not all_jobs:
        print('No jobs scraped, exiting without sample data')
        return
    
    processed_jobs = process_with_gemini(all_jobs)
    
    if not processed_jobs:
        print('No jobs processed successfully')
        return
    
    inserted_count = sum(1 for job in processed_jobs if insert_job(job))
    deleted_count = cleanup_expired_jobs()
    
    print(f'Pipeline complete. Inserted: {inserted_count}, Deleted expired: {deleted_count}')

if __name__ == '__main__':
    main()