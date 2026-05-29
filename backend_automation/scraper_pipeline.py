import os
import json
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Any

import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import google.generativeai as genai

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError('SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set')

if not GEMINI_API_KEY:
    raise ValueError('GEMINI_API_KEY environment variable must be set')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SOURCES = [
    {
        'name': 'mock_sarkari_jobs',
        'url': 'https://www.sarkariresult.com/',
        'type': 'html'
    }
]

ORGANIZATION_MAPPING = {
    'SSC': ['ssc', 'staff selection commission'],
    'UPSC': ['upsc', 'union public service commission'],
    'Railways': ['railway', 'indian railway', 'rpf', 'rrb'],
    'Banking': ['bank', 'ibps', 'sbi', 'po'],
    'Defence': ['defence', 'nda', 'cds', 'indian navy', 'indian army', 'indian air force']
}

def normalize_organization(text: str) -> str:
    text_lower = text.lower()
    for org, keywords in ORGANIZATION_MAPPING.items():
        for keyword in keywords:
            if keyword in text_lower:
                return org
    return 'Other'

def scrape_sarkari_results() -> List[Dict[str, Any]]:
    jobs = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get('https://www.sarkariresult.com/', headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if not text or len(text) < 10:
                continue
                
            if any(keyword in text.lower() for keyword in ['recruitment', 'vacancy', 'online', 'apply', 'notification']):
                full_url = href if href.startswith('http') else f'https://www.sarkariresult.com/{href}'
                jobs.append({
                    'title': text,
                    'raw_content': f'Title: {text}\nLink: {full_url}',
                    'link': full_url
                })
                
    except Exception as e:
        print(f'Error scraping sarkariresult.com: {e}')
    
    return jobs[:20]

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    processed_jobs = []
    
    for job in raw_jobs:
        prompt = f"""
Extract and structure the following job information into valid JSON format:

Raw Content: {job['raw_content']}

Return ONLY a valid JSON object with the following fields (no markdown, no extra text):
- title: string (cleaned job title, max 100 chars)
- organization: one of ("SSC", "UPSC", "Railways", "Banking", "Defence", "Other")
- total_vacancies: string (e.g., "400+" or "1,000+" or null)
- start_date: string in YYYY-MM-DD format or null
- last_date: string in YYYY-MM-DD format (mandatory, estimate if needed)
- fee_details: string (application fees or "As per official notification")
- eligibility: string (age, education requirements)
- official_apply_link: string (the registration URL)

If you cannot extract last_date, use a far future date like "2026-12-31".
"""
        
        try:
            response = model.generate_content(prompt)
            json_text = response.text.strip()
            
            if json_text.startswith('```json'):
                json_text = json_text[7:]
            if json_text.endswith('```'):
                json_text = json_text[:-3]
            
            parsed = json.loads(json_text.strip())
            
            parsed['organization'] = normalize_organization(parsed.get('title', ''))
            
            if not parsed.get('last_date'):
                parsed['last_date'] = '2026-12-31'
            
            if not parsed.get('official_apply_link'):
                parsed['official_apply_link'] = job.get('link', '')
            
            processed_jobs.append(parsed)
            
        except Exception as e:
            print(f'Error processing job with Gemini: {e}')
            continue
    
    return processed_jobs

def deduplicate_and_insert(jobs: List[Dict[str, Any]]) -> int:
    inserted_count = 0
    
    for job in jobs:
        try:
            existing = supabase.table('jobs').select('id').eq('title', job['title']).eq('organization', job['organization']).execute()
            
            if existing.data:
                print(f'Skipping existing job: {job["title"]}')
                continue
            
            job_data = {
                'title': job['title'],
                'organization': job['organization'],
                'total_vacancies': job.get('total_vacancies', 'Not specified'),
                'start_date': job.get('start_date'),
                'last_date': job['last_date'],
                'fee_details': job.get('fee_details', 'As per official notification'),
                'eligibility': job.get('eligibility', 'Not specified'),
                'official_apply_link': job['official_apply_link']
            }
            
            result = supabase.table('jobs').insert(job_data).execute()
            
            if result.data:
                inserted_count += 1
                print(f'Inserted job: {job["title"]}')
                
        except Exception as e:
            print(f'Error inserting job {job.get("title")}: {e}')
    
    return inserted_count

def cleanup_expired_jobs() -> int:
    today = date.today().isoformat()
    
    try:
        result = supabase.table('jobs').delete().lt('last_date', today).execute()
        deleted_count = len(result.data) if result.data else 0
        print(f'Deleted {deleted_count} expired jobs')
        return deleted_count
    except Exception as e:
        print(f'Error cleaning up expired jobs: {e}')
        return 0

def main():
    print('Starting Sarkari Jobs scraping pipeline...')
    
    print('Step 1: Scraping source websites...')
    raw_jobs = scrape_sarkari_results()
    print(f'Found {len(raw_jobs)} potential job listings')
    
    if not raw_jobs:
        print('No jobs found, exiting...')
        return
    
    print('Step 2: Processing with Gemini AI...')
    processed_jobs = process_with_gemini(raw_jobs)
    print(f'Processed {len(processed_jobs)} jobs')
    
    if not processed_jobs:
        print('No valid jobs after processing, exiting...')
        return
    
    print('Step 3: Inserting into Supabase (with deduplication)...')
    inserted = deduplicate_and_insert(processed_jobs)
    print(f'Inserted {inserted} new jobs')
    
    print('Step 4: Cleaning up expired jobs...')
    deleted = cleanup_expired_jobs()
    print(f'Cleanup complete: {deleted} expired jobs removed')
    
    print(f'Pipeline complete. Total inserted: {inserted}, expired removed: {deleted}')

if __name__ == '__main__':
    main()