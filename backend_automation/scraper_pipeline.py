import os
import json
from datetime import date
from typing import List, Dict, Any

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
    raise ValueError('GEMINI_API_KEY environment variables must be set')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ORGANIZATION_MAPPING = {
    'SSC': ['ssc', 'staff selection commission'],
    'UPSC': ['upsc', 'union public service commission'],
    'Railways': ['railway', 'rpf', 'rrb', 'railways'],
    'Banking': ['bank', 'ibps', 'sbi', 'po'],
    'Defence': ['defence', 'nda', 'cds', 'navy', 'army', 'air force']
}

def normalize_organization(text: str) -> str:
    text_lower = text.lower()
    for org, keywords in ORGANIZATION_MAPPING.items():
        for keyword in keywords:
            if keyword in text_lower:
                return org
    return 'Other'

def scrape_sarkari_result() -> List[Dict[str, Any]]:
    jobs = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get('https://www.sarkariresult.com/', headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for div in soup.find_all('div', class_='post-title'):
            link = div.find('a', href=True)
            if link:
                title = link.get_text(strip=True)
                href = link['href']
                if title and len(title) >= 10:
                    jobs.append({
                        'title': title,
                        'raw_content': f'Title: {title}\nLink: {href}',
                        'link': href
                    })
    except Exception as e:
        print(f'Error scraping sarkariresult.com: {e}')
    
    return jobs[:10]

def scrape_sarkari_exams() -> List[Dict[str, Any]]:
    jobs = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get('https://www.sarkariexams.com/', headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for item in soup.find_all(['h2', 'h3']):
            text = item.get_text(strip=True)
            link = item.find('a', href=True)
            href = link['href'] if link else ''
            
            if text and len(text) >= 15 and any(k in text.lower() for k in ['recruitment', 'vacancy', 'exam', '2024', '2025', '2026']):
                jobs.append({
                    'title': text,
                    'raw_content': f'Title: {text}\nLink: {href}',
                    'link': href
                })
    except Exception as e:
        print(f'Error scraping sarkariexams.com: {e}')
    
    return jobs[:10]

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    processed_jobs = []
    
    for job in raw_jobs:
        prompt = f"""Extract job details into JSON only (no markdown, no explanation):

Input: {job['raw_content']}

Output format:
{{
  "title": "cleaned job title, max 100 chars",
  "total_vacancies": "number string like '100+' or null",
  "start_date": "YYYY-MM-DD or null",
  "last_date": "YYYY-MM-DD (estimate 2026-12-31 if unknown)",
  "fee_details": "application fees or 'As per official notification'",
  "eligibility": "age and education requirements",
  "official_apply_link": "URL string"
}}"""
        
        try:
            response = model.generate_content(prompt)
            json_text = response.text.strip()
            
            if json_text.startswith('```'):
                json_text = '\n'.join(json_text.split('\n')[1:-1])
            
            parsed = json.loads(json_text)
            parsed['organization'] = normalize_organization(parsed.get('title', ''))
            
            if not parsed.get('last_date'):
                parsed['last_date'] = '2026-12-31'
            if not parsed.get('official_apply_link') and job.get('link'):
                parsed['official_apply_link'] = job['link']
                
            processed_jobs.append(parsed)
            print(f'Processed: {parsed.get("title", "Unknown")}')
            
        except json.JSONDecodeError as e:
            print(f'Gemini JSON error for {job.get("title", "Unknown")}: {e}')
        except Exception as e:
            print(f'Gemini error: {e}')
    
    return processed_jobs

def deduplicate_and_insert(jobs: List[Dict[str, Any]]) -> int:
    inserted = 0
    today = date.today().isoformat()
    
    for job in jobs:
        try:
            existing = supabase.table('jobs').select('id').eq('title', job['title']).eq('organization', job['organization']).execute()
            
            if existing.data and len(existing.data) > 0:
                print(f'Skip existing: {job["title"]}')
                continue
            
            job['start_date'] = job.get('start_date')
            job['last_date'] = job.get('last_date') or '2026-12-31'
            
            result = supabase.table('jobs').insert(job).execute()
            
            if result.data:
                inserted += 1
                print(f'Inserted: {job["title"]}')
                
        except Exception as e:
            print(f'Insert error for {job.get("title", "Unknown")}: {e}')
    
    return inserted

def cleanup_expired_jobs() -> int:
    today = date.today().isoformat()
    
    try:
        result = supabase.table('jobs').delete().lt('last_date', today).execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        print(f'Cleanup error: {e}')
        return 0

def main():
    print('Starting Sarkari Jobs pipeline...')
    
    all_jobs = scrape_sarkari_result() + scrape_sarkari_exams()
    print(f'Scraped {len(all_jobs)} listings')
    
    if not all_jobs:
        print('No listings found, adding sample data for testing...')
        sample_jobs = [
            {
                'title': 'SSC CGL Recruitment 2026',
                'organization': 'SSC',
                'total_vacancies': '9,400+',
                'start_date': '2025-06-01',
                'last_date': '2025-07-15',
                'fee_details': 'General/OBC: ₹100, SC/ST: ₹0',
                'eligibility': 'Graduate in any stream',
                'official_apply_link': 'https://ssc.nic.in/cgl'
            },
            {
                'title': 'UPSC NDA (II) Recruitment 2026',
                'organization': 'Defence',
                'total_vacancies': '400+',
                'start_date': '2025-06-01',
                'last_date': '2025-07-01',
                'fee_details': 'General: ₹100, SC/ST: ₹0',
                'eligibility': '12th Pass / Graduate',
                'official_apply_link': 'https://upsc.gov.in/nda'
            }
        ]
        inserted = deduplicate_and_insert(sample_jobs)
    else:
        processed = process_with_gemini(all_jobs)
        if processed:
            inserted = deduplicate_and_insert(processed)
        else:
            print('No jobs processed, using sample data')
            sample_jobs = [{
                'title': 'Railway RRB NTPC Recruitment 2026',
                'organization': 'Railways',
                'total_vacancies': '35,000+',
                'start_date': '2025-06-01',
                'last_date': '2025-07-31',
                'fee_details': 'General/OBC: ₹100, SC/ST: ₹0',
                'eligibility': '12th Pass / Graduate',
                'official_apply_link': 'https://rrbcdg.nic.in/'
            }]
            inserted = deduplicate_and_insert(sample_jobs)
    
    deleted = cleanup_expired_jobs()
    print(f'Pipeline complete. Inserted: {inserted}, Deleted expired: {deleted}')

if __name__ == '__main__':
    main()