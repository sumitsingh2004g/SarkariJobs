import os
import json
import time
import random
import re
from datetime import date
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from curl_cffi import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
from google import genai

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError('SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set')
if not GEMINI_API_KEY:
    raise ValueError('GEMINI_API_KEY environment variable must be set')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

EXCLUDED_PATTERNS = [
    'freejobalert', 'sarkariresult', 'download app', 'sarkari result'
]

def polite_delay():
    time.sleep(random.uniform(2, 4))

def extract_clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav', 'aside', 'svg', 'img', 'iframe']):
        tag.decompose()
    
    main_content = soup.find(['article', 'main'])
    if not main_content:
        for selector in ['div.content', 'div.entry-content', 'div.post-content', 'div.article-content', 'div.main-content']:
            main_content = soup.select_one(selector)
            if main_content:
                break
    
    if not main_content:
        candidates = soup.find_all('div')
        for c in candidates:
            text_len = len(c.get_text(strip=True))
            if text_len > 500 and not c.find(['a', 'ul', 'ol'], recursive=False):
                main_content = c
                break
    
    if main_content:
        text = main_content.get_text(separator='\n', strip=True)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return '\n'.join(lines)[:5000]
    return soup.get_text(separator='\n', strip=True)[:5000]

def is_navbar_link(href: str) -> bool:
    if not href:
        return True
    href_lower = href.lower()
    navbar_patterns = [
        '/about', '/privacy', '/terms', '/contact', '/sitemap', '/rss', '/feed',
        '/admitcard', '/answerkey', '/syllabus', '/certificate', '/rollno', '/mocktest',
        '/state-government-jobs', '/category/', '/tag/', '/author/'
    ]
    for pattern in navbar_patterns:
        if pattern in href_lower:
            return True
    if re.search(r'/(home|facebook|twitter|instagram|linkedin|youtube|wp-content)/', href_lower):
        return True
    return False

def is_excluded_title(title: str) -> bool:
    if not title:
        return True
    t = title.lower()
    for pattern in EXCLUDED_PATTERNS:
        if pattern in t:
            return True
    if 'download' in t and 'app' in t:
        return True
    return False

def is_valid_url(url: Optional[str]) -> bool:
    if not url or not isinstance(url, str):
        return False
    return url.startswith(('http://', 'https://'))

def extract_govt_links(text: str) -> List[str]:
    govt_links = []
    pattern1 = r'https?://[^\s\'"<>]+?\.(?:gov\.in|nic\.in)[^\s\'"<>]*'
    pattern2 = r'https?://[^\s\'"<>]+?\.gov[^\s\'"<>]*'
    for pattern in [pattern1, pattern2]:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            cleaned = m.rstrip('.,;:')
            if cleaned and len(cleaned) > 20:
                govt_links.append(cleaned)
    return list(dict.fromkeys(govt_links))[:3]

def scrape_freejobalert_index() -> List[Dict[str, str]]:
    jobs = []
    base_url = 'https://www.freejobalert.com/'
    seen = set()
    
    try:
        resp = requests.get(base_url, impersonate="chrome", timeout=20)
        print(f"FreeJobAlert response: {resp.status_code}, len={len(resp.text)}")
        polite_delay()
        
        if resp.status_code != 200:
            return jobs
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        all_links = soup.find_all('a', href=True)
        print(f"Found {len(all_links)} total links on page")
        
        for a in all_links:
            href = a['href']
            txt = a.get_text(strip=True)
            
            if not href or not txt:
                continue
            if len(txt) < 20:
                continue
            if is_navbar_link(href):
                continue
            
            full_url = href if href.startswith('http') else urljoin(base_url, href)
            href_lower = full_url.lower()
            
            job_patterns = ['/202[4-9]', '/recruitment', '/vacancy', '/notification', '/online', '/2024', '/2025', '/2026', '/apply']
            if any(p in href_lower for p in job_patterns):
                if full_url not in seen:
                    seen.add(full_url)
                    jobs.append({'url': full_url, 'text': txt})
            elif '/sarkari-result/' in href_lower or re.search(r'/[\w\-]+-\d{4}/', href_lower):
                if full_url not in seen:
                    seen.add(full_url)
                    jobs.append({'url': full_url, 'text': txt})
        print(f"Matched {len(jobs)} job links")
        
    except Exception as e:
        print(f"Error scraping FreeJobAlert index: {e}")
    
    return jobs

def scrape_sarkariresult_index() -> List[Dict[str, str]]:
    jobs = []
    base_url = 'https://www.sarkariresult.com/latestjob/'
    seen = set()
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        resp = requests.get(base_url, impersonate="chrome", headers=headers, timeout=20)
        print(f"SarkariResult response: {resp.status_code}, len={len(resp.text)}")
        polite_delay()
        
        if resp.status_code != 200:
            return jobs
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        all_links = soup.find_all('a', href=True)
        print(f"Found {len(all_links)} total links on page")
        
        for a in all_links:
            href = a['href']
            txt = a.get_text(strip=True)
            
            if not href or not txt:
                continue
            if len(txt) < 20:
                continue
            if is_navbar_link(href):
                continue
            
            full_url = href if href.startswith('http') else f'https://sarkariresult.com{href}'
            href_lower = full_url.lower()
            
            if not re.search(r'/(202[4-9]|upsssc|ups[cs]|rrb|ssc|bank|defence|nda|navy|army|railway|rpf)/', href_lower):
                continue
            
            if full_url not in seen:
                seen.add(full_url)
                jobs.append({'url': full_url, 'text': txt})
        print(f"Matched {len(jobs)} job links")
        
    except Exception as e:
        print(f"Error scraping SarkariResult index: {e}")
    
    return jobs

def scrape_job_deep_page(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, impersonate="chrome", timeout=20)
        polite_delay()
        
        if resp.status_code != 200:
            return None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        content = extract_clean_text(soup)
        
        if content and len(content.strip()) > 100:
            return content
        return None
    except Exception as e:
        print(f"Error fetching deep page {url}: {e}")
        return None

def normalize_organization(title: str) -> str:
    mapping = {
        'SSC': ['ssc', 'staff selection'],
        'UPSC': ['upsc', 'union public service commission'],
        'Railways': ['railway', 'rpf', 'rrb', 'rail'],
        'Banking': ['bank', 'ibps', 'sbi', 'ppo', 'clerks'],
        'Defence': ['defence', 'nda', 'cds', 'navy', 'army', 'air force'],
        'State': ['state', 'up', 'bihar', 'tamil', 'telangana', 'karnataka', 'mp ', 'madhya']
    }
    t = (title or '').lower()
    for org, keywords in mapping.items():
        if any(kw in t for kw in keywords):
            return org
    return 'Other'

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_jobs:
        return []
    
    instruction = (
        "You are an expert data parser. Do NOT use placeholder dates like 31-12-2026 or fallback website domains like sarkariresult.com. "
        "Do NOT use the current year (2026) as a placeholder for vacancies or dates. "
        "Extract ONLY from the provided text. Return valid JSON with these exact fields:\n\n"
        "{\n"
        '  "title": "Actual job title (e.g., SSC MTS 2024, Bank Clerk Recruitment)",\n'
        '  "total_vacancies": "Exact number (e.g., 1400, 1607, 457) or \"Not specified\" if not found. If you cannot find explicit numerical value, output \"Not specified\". Do NOT use the current year (2026) as a placeholder for vacancies or dates.",\n'
        '  "apply_link": "Official government website link ending in .gov.in or .nic.in ONLY. If official government link present in text, extract it. Otherwise output null.",\n'
        '  "start_date": "Application start date or null",\n'
        '  "last_date": "Application deadline date or null",\n'
        '  "application_fees": "Fee amount (e.g., Rs. 100/-, 125) or null",\n'
        '  "eligibility": "Required qualification (e.g., Graduate, 12th pass) or null"\n'
        "}\n\n"
        "Rules:\n"
        "- Skip if title contains: FreeJobAlert, SarkariResult, Download App\n"
        "- Extract vacancy count from 'Total Vacancy', 'Vacancy', 'Posts', or table cells only. Do NOT hallucinate vacancy numbers.\n"
        "- Find apply_link in .gov.in/.nic.in URLs from page text - use REAL official links only\n"
        "- Dates: Use format as written in notification (DD/MM/YYYY or Month DD, YYYY). Do NOT invent dates.\n"
    )
    
    results = []
    for job in raw_jobs:
        title = job.get('text', '')
        
        if is_excluded_title(title):
            print(f"Skipping excluded title: {title[:50]}")
            continue
        
        data = {}
        for attempt in range(5):
            try:
                prompt = f"{instruction}\n\nJob Title: {title}\n\nPage Content:\n{job.get('content', '')[:4000]}"
                response = gemini_client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt
                )
                txt = response.text.strip()
                json_match = re.search(r'\{.*\}', txt, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                else:
                    data = {}
                break
            except Exception as e:
                if '429' in str(e) and attempt < 4:
                    wait_time = (attempt + 1) * 20 + random.uniform(0, 5)
                    print(f"Rate limited, waiting {wait_time:.1f}s before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"Gemini error for {title[:30]}: {e}")
        
        govt_links = extract_govt_links(job.get('content', ''))
        
        apply_link = data.get('apply_link')
        if apply_link and not is_valid_url(apply_link):
            apply_link = None

        if not apply_link:
            for candidate in govt_links + [job.get('url', '')]:
                if is_valid_url(candidate):
                    apply_link = candidate
                    break
        
        extracted_vacancies = data.get('total_vacancies')
        if not extracted_vacancies:
            vac_match = re.search(r'(?:total\s*vacanc(?:y|ies)?|posts?)[:\-]?\s*(\d{1,2}(?:[,]\d{3})*)', job.get('content', ''), re.IGNORECASE)
            if vac_match:
                vacancy_str = vac_match.group(1).replace(',', '').strip()
                try:
                    vac_num = int(vacancy_str)
                    if 1 <= vac_num <= 50000:
                        extracted_vacancies = vacancy_str
                except ValueError:
                    pass
            else:
                extracted_vacancies = 'Not specified'
        
        extracted_last_date = data.get('last_date')
        if not extracted_last_date:
            date_patterns = [
                r'(?:last\s*date|deadline|applying\s*upto)[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
            ]
            for pattern in date_patterns:
                date_match = re.search(pattern, job.get('content', ''), re.IGNORECASE)
                if date_match:
                    extracted_last_date = date_match.group(1).replace('/', '-')
                    break
        
        extracted_start_date = data.get('start_date')
        if not extracted_start_date:
            start_match = re.search(r'(?:start\s*date|application\s*start)[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})', job.get('content', ''), re.IGNORECASE)
            if start_match:
                extracted_start_date = start_match.group(1).replace('/', '-')
        
        final_last_date = extracted_last_date
        if extracted_last_date and '-' in extracted_last_date:
            parts = extracted_last_date.split('-')
            if len(parts[0]) == 4 and len(parts) == 3:
                final_last_date = '-'.join(parts)
            elif len(parts[0]) <= 2 and len(parts) == 3:
                final_last_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        
        results.append({
            'title': data.get('title') or title,
            'organization': normalize_organization(data.get('title') or title),
            'total_vacancies': str(extracted_vacancies or 'Not specified'),
            'start_date': extracted_start_date,
            'last_date': final_last_date,
            'fee_details': str(data.get('application_fees') or 'As per official notification'),
            'eligibility': str(data.get('eligibility') or 'As per official notification'),
            'official_apply_link': apply_link
        })
        print(f"Processed: {title[:30]} -> vacancies={extracted_vacancies or 'Not specified'}, last_date={final_last_date}, apply={apply_link[:50] if apply_link else 'N/A'}...")
    
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
        print(f"Deleted {len(r.data or [])} expired jobs")
    except Exception as e:
        print(f"Cleanup error: {e}")

def main():
    print('Starting Deep Scraper Pipeline...')
    
    # FORCE TRUNCATE: Clear all existing stale data before fresh crawl
    try:
        supabase.table('jobs').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        print("Cleared existing jobs table data")
    except Exception as e:
        print(f"Truncate error: {e}")
    
    fja_index = scrape_freejobalert_index()
    print(f"FreeJobAlert index links found: {len(fja_index)}")
    
    sr_index = scrape_sarkariresult_index()
    print(f"SarkariResult index links found: {len(sr_index)}")
    
    all_raw_jobs = []
    
    for link in fja_index[:15]:
        content = scrape_job_deep_page(link['url'])
        if content:
            all_raw_jobs.append({'text': link['text'], 'url': link['url'], 'content': content})
    
    for link in sr_index[:15]:
        content = scrape_job_deep_page(link['url'])
        if content:
            all_raw_jobs.append({'text': link['text'], 'url': link['url'], 'content': content})
    
    print(f"Deep pages scraped: {len(all_raw_jobs)}")
    
    if not all_raw_jobs:
        print("No jobs found to process, skipping insertion")
        return
    
    processed = process_with_gemini(all_raw_jobs)
    inserted_count = 0
    for j in processed:
        try:
            supabase.table('jobs').upsert(j).execute()
            print(f"Upserted: {j.get('title')}")
            inserted_count += 1
        except Exception as e:
            print(f"Insert error: {e}")
    print(f"Inserted {inserted_count} jobs")
    cleanup_expired()
    print('Pipeline complete.')

if __name__ == '__main__':
    main()