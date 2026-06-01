import os
import json
import time
from datetime import date
from typing import List, Dict, Any

from curl_cffi import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError('SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set')
if not GEMINI_API_KEY:
    raise ValueError('GEMINI_API_KEY environment variable must be set')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configure Gemini
import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)

ORGANIZATION_MAPPING = {
    'SSC': ['ssc', 'staff selection commission'],
    'UPSC': ['upsc', 'union public service commission'],
    'Railways': ['railway', 'rpf', 'rrb'],
    'Banking': ['bank', 'ibps', 'sbi', 'po'],
    'Defence': ['defence', 'nda', 'cds', 'navy', 'army']
}

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
    
    urls_to_try = [
        'https://www.sarkariresult.com/latestjob/',
        'https://www.sarkariresult.com/rss.php',
    ]
    
    for url in urls_to_try:
        try:
            response = requests.get(url, impersonate="chrome", timeout=15)
            
            print(f'sarkariresult ({url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for div in soup.find_all(['div', 'table'], class_=lambda x: x and any(k in str(x).lower() for k in ['latestjob', 'job', 'list', 'content', 'post'])):
                for link in div.find_all('a', href=True):
                    title = link.get_text(strip=True)
                    if title and len(title) >= 10:
                        href = link['href']
                        full_url = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                        jobs.append({
                            'title': title,
                            'raw_content': f'Title: {title}\nLink: {full_url}',
                            'link': full_url
                        })
            
            for tr in soup.find_all('tr'):
                for link in tr.find_all('a', href=True):
                    title = link.get_text(strip=True)
                    if title and len(title) >= 10:
                        href = link['href']
                        full_url = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                        jobs.append({
                            'title': title,
                            'raw_content': f'Title: {title}\nLink: {full_url}',
                            'link': full_url
                        })
            
            for link in soup.find_all('a', href=True):
                title = link.get_text(strip=True)
                if title and len(title) >= 15 and any(k in title.lower() for k in ['recruitment', '2024', '2025', '2026', 'vacancy', 'notification', 'exam']):
                    href = link['href']
                    full_url = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                    jobs.append({
                        'title': title,
                        'raw_content': f'Title: {title}\nLink: {full_url}',
                        'link': full_url
                    })
            
            print(f'sarkariresult ({url}): Found {len(jobs)} listings')
            if jobs:
                return jobs[:20]
        except Exception as e:
            print(f'sarkariresult ({url}) error: {type(e).__name__}: {e}')
        time.sleep(2)
    
    return jobs[:20]

def scrape_freejobalert() -> List[Dict[str, Any]]:
    jobs = []
    
    urls = ['https://www.freejobalert.com/', 'https://freejobalert.com/']
    
    for url in urls:
        try:
            response = requests.get(url, impersonate="chrome", timeout=15)
            
            print(f'freejobalert ({url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for tr in soup.find_all('tr'):
                row_text = tr.get_text()
                if any(k in row_text.lower() for k in ['recruitment', 'vacancy', 'notification', '2024', '2025', '2026', 'apply']):
                    for link in tr.find_all('a', href=True):
                        title = link.get_text(strip=True)
                        if title and len(title) >= 10:
                            href = link['href']
                            full_url = href if href.startswith('http') else f'https://freejobalert.com{href}'
                            jobs.append({
                                'title': title,
                                'raw_content': f'Title: {title}\nLink: {full_url}',
                                'link': full_url
                            })
            
            print(f'freejobalert ({url}): Found {len(jobs)} listings via BeautifulSoup')
            if jobs:
                return jobs[:20]
        except Exception as e:
            print(f'freejobalert ({url}) error: {type(e).__name__}: {e}')
        time.sleep(2)
    
    return jobs[:20]

def scrape_sarkari_exams() -> List[Dict[str, Any]]:
    jobs = []
    
    urls = ['https://www.sarkariexams.com/', 'https://sarkariexams.com/']
    
    for url in urls:
        try:
            response = requests.get(url, impersonate="chrome", timeout=15)
            
            print(f'sarkariexams ({url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for h in soup.find_all(['h2', 'h3', 'h4']):
                text = h.get_text(strip=True)
                if text and len(text) >= 15 and any(k in text.lower() for k in ['recruitment', 'vacancy', '2024', '2025', '2026', 'exam', 'notification']):
                    jobs.append({
                        'title': text,
                        'raw_content': f'Title: {text}\nLink: {url}',
                        'link': url
                    })
            
            print(f'sarkariexams ({url}): Found {len(jobs)} listings via BeautifulSoup')
            if jobs:
                return jobs[:15]
        except Exception as e:
            print(f'sarkariexams ({url}) error: {type(e).__name__}: {e}')
        time.sleep(2)
    
    return jobs[:15]

def scrape_indeed_govt() -> List[Dict[str, Any]]:
    jobs = []
    
    url = 'https://in.indeed.com/jobs?q=government+jobs&jt=fulltime'
    
    try:
        response = requests.get(url, impersonate="chrome", timeout=15)
        
        print(f'indeed govt ({url}): Status {response.status_code}')
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for h in soup.find_all(['h2', 'h3']):
                text = h.get_text(strip=True)
                if text and len(text) >= 15 and any(k in text.lower() for k in ['government', 'recruitment', 'vacancy']):
                    jobs.append({
                        'title': text,
                        'raw_content': f'Title: {text}\nLink: {url}',
                        'link': url
                    })
            
            print(f'indeed govt: Found {len(jobs)} listings')
            return jobs[:15]
    except Exception as e:
        print(f'indeed govt error: {type(e).__name__}: {e}')
    
    return jobs[:15]

def scrape_joberr_govt() -> List[Dict[str, Any]]:
    jobs = []
    
    url = 'https://www.joberr.com/govt-jobs'
    
    try:
        response = requests.get(url, impersonate="chrome", timeout=15)
        
        print(f'joberr ({url}): Status {response.status_code}')
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for div in soup.find_all(['div', 'article'], class_=lambda x: x and any(k in str(x).lower() for k in ['job', 'post', 'entry'])):
                for link in div.find_all('a', href=True):
                    title = link.get_text(strip=True)
                    if title and len(title) >= 10:
                        href = link['href']
                        full_url = href if href.startswith('http') else f'https://www.joberr.com{href}'
                        jobs.append({
                            'title': title,
                            'raw_content': f'Title: {title}\nLink: {full_url}',
                            'link': full_url
                        })
            
            print(f'joberr: Found {len(jobs)} listings')
            return jobs[:15]
    except Exception as e:
        print(f'joberr error: {type(e).__name__}: {e}')
    
    return jobs[:15]

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_jobs:
        return []

    processed_jobs = []
    model = genai.GenerativeModel('gemini-1.5-flash')  # or pro

    system_instruction = (
        "You are an expert at extracting structured information from Indian government job recruitment notices. "
        "Given the full text of a job vacancy inner page, extract:\n"
        "1. total_vacancies: Look explicitly for fields like 'Total Vacancy', 'Total Posts', or table cells indicating numbers (e.g., '1400+'). "
        "If a breakdown is provided (e.g., 'Category-wise: 100 UR, 50 OBC, ...'), sum them or take the total if explicitly stated. "
        "Do NOT default to 'Not specified' if the text contains any numeric vacancy information. "
        "If no vacancy number can be found, return 'Not specified'.\n"
        "2. official_apply_link: Locate and extract the actual government official website domain or registration link. "
        "Look for links containing '.gov.in', '.nic.in', or text explicitly labeled 'Official Website Link', 'Apply Online', 'Registration Link', etc. "
        "If multiple such links exist, prefer the one that appears to be the official application portal. "
        "Do NOT return the source page URL (e.g., freejobalert.com). If no official link is found, return the source page URL as fallback.\n"
        "Return your answer as a JSON object with exactly two keys: 'total_vacancies' (string) and 'official_apply_link' (string). "
        "Do not include any extra text."
    )

    for job in raw_jobs:
        org = normalize_organization(job.get('title', ''))
        # Default values
        total_vacancies = 'Not specified'
        official_apply_link = job.get('link', '')  # fallback to source link

        try:
            # Fetch inner page
            resp = requests.get(job['link'], impersonate="chrome", timeout=15)
            if resp.status_code == 200:
                # Extract text
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Remove script/style
                for tag in soup(['script', 'style', 'noscript']):
                    tag.decompose()
                text = soup.get_text(separator=' ', strip=True)
                # Limit length to avoid exceeding token limits (approx 4000 chars)
                if len(text) > 8000:
                    text = text[:8000]

                # Prepare prompt
                prompt = f"{system_instruction}\n\nJob Title: {job.get('title', '')}\n\nPage Content:\n{text}"

                # Call Gemini
                response = model.generate_content(prompt)
                result_text = response.text.strip()

                # Try to parse JSON
                import json
                # Find JSON block
                start = result_text.find('{')
                end = result_text.rfind('}')
                if start != -1 and end != -1 and start < end:
                    json_str = result_text[start:end+1]
                    data = json.loads(json_str)
                    total_vacancies = data.get('total_vacancies', 'Not specified')
                    official_apply_link = data.get('official_apply_link', job.get('link', ''))
                    # Ensure official_apply_link is a string
                    if not isinstance(official_apply_link, str):
                        official_apply_link = str(official_apply_link)
                else:
                    # Fallback: try to extract lines
                    lines = result_text.split('\n')
                    for line in lines:
                        if 'total_vacancies' in line.lower():
                            # naive extraction
                            pass
        except Exception as e:
            print(f"Gemini processing error for {job.get('title')}: {e}")

        processed_job = {
            'title': job.get('title', ''),
            'organization': org,
            'total_vacancies': total_vacancies,
            'start_date': None,
            'last_date': '2026-12-31',
            'fee_details': 'As per official notification',
            'eligibility': 'Not specified',
            'official_apply_link': official_apply_link
        }
        print(f'AI processed: {processed_job["title"]} -> vacancies: {processed_job["total_vacancies"]}, link: {processed_job["official_apply_link"]}')
        processed_jobs.append(processed_job)

    return processed_jobs

def insert_job(job: Dict[str, Any]) -> bool:
    try:
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
    time.sleep(2)
    all_jobs.extend(scrape_joberr_govt())
    
    total_scraped = len(all_jobs)
    print(f'Total scraped: {total_scraped} listings')
    
    if total_scraped == 0:
        print('No jobs scraped - adding test connection job - Run V2')
        all_jobs.append({
            'title': f'Test Connection Job - Run V2 - {int(time.time())}',
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