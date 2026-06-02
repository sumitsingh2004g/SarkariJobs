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
    raise ValueError('GEMINI_API_KEY environment variable must be set')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configure Gemini
import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)

MAX_DEPTH = 2
POLITE_DELAY_MIN = 2
POLITE_DELAY_MAX = 3

IGNORED_URL_PATTERNS = [
    r'about[-_]?us',
    r'privacy[-_]?policy',
    r'terms[-_]?and[-_]?conditions',
    r'contact[-_]?us',
    r'sitemap',
    r'rss',
    r'feed',
    r'\.pdf$',
    r'facebook\.com',
    r'twitter\.com',
    r'instagram\.com',
    r'linkedin\.com',
    r'youtube\.com',
    r'share',
    r'wp-content',
    r'wp-admin',
    r'#',
    r'javascript:',
]

JOB_URL_PATTERNS = [
    r'recruitment',
    r'vacancy',
    r'notification',
    r'exam',
    r'admit[-_]?card',
    r'2024',
    r'2025',
    r'2026',
    r'sarkari',
    r'job',
    r'post',
    r'apply',
    r'online[-_]?apply',
    r'official',
]

def polite_delay():
    delay = random.uniform(POLITE_DELAY_MIN, POLITE_DELAY_MAX)
    time.sleep(delay)

def is_ignored_url(url: str) -> bool:
    url_lower = url.lower()
    for pattern in IGNORED_URL_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    return False

def is_job_related_url(url: str, text: str) -> bool:
    if is_ignored_url(url):
        return False
    combined = (url + ' ' + text).lower()
    for pattern in JOB_URL_PATTERNS:
        if re.search(pattern, combined):
            return True
    return False

def normalize_organization(text: str) -> str:
    ORGANIZATION_MAPPING = {
        'SSC': ['ssc', 'staff selection commission'],
        'UPSC': ['upsc', 'union public service commission'],
        'Railways': ['railway', 'rpf', 'rrb'],
        'Banking': ['bank', 'ibps', 'sbi', 'po'],
        'Defence': ['defence', 'nda', 'cds', 'navy', 'army']
    }
    if not text:
        return 'Other'
    text_lower = text.lower()
    for org, keywords in ORGANIZATION_MAPPING.items():
        for keyword in keywords:
            if keyword in text_lower:
                return org
    return 'Other'

def extract_table_text(soup: BeautifulSoup) -> str:
    tables = soup.find_all('table')
    extracted = []
    for table in tables:
        rows = []
        for tr in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if cells:
                rows.append(' | '.join(cells))
        if rows:
            extracted.append('\n'.join(rows))
    return '\n\n'.join(extracted)

def extract_article_text(soup: BeautifulSoup) -> str:
    for tag in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav']):
        tag.decompose()
    
    article = soup.find(['article', 'main', 'div.content', 'div.entry-content', 'div.post-content'])
    if article:
        return article.get_text(separator=' ', strip=True)
    
    candidates = []
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if len(text) > 50:
            candidates.append(text)
    if candidates:
        return '\n'.join(candidates[:20])
    
    return soup.get_text(separator=' ', strip=True)

def extract_targeted_content(soup: BeautifulSoup) -> str:
    table_text = extract_table_text(soup)
    article_text = extract_article_text(soup)
    
    if table_text and len(table_text) > 100:
        return f"TABLE DATA:\n{table_text}\n\nARTICLE TEXT:\n{article_text[:2000]}"
    
    return article_text[:4000]

def crawl_page(
    url: str,
    base_domain: str,
    current_depth: int,
    visited_urls: set,
    parent_title: str = ''
) -> Optional[Dict[str, Any]]:
    if current_depth > MAX_DEPTH:
        return None
    
    if url in visited_urls:
        return None
    
    visited_urls.add(url)
    
    try:
        print(f"[Depth {current_depth}] Crawling: {url}")
        response = requests.get(url, impersonate="chrome", timeout=15)
        polite_delay()
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        if current_depth == MAX_DEPTH:
            content = extract_targeted_content(soup)
            return {
                'title': parent_title,
                'link': url,
                'content_for_gemini': content,
                'depth': current_depth
            }
        
        job_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            link_text = link.get_text(strip=True)
            
            if not href or not link_text or len(link_text) < 10:
                continue
            
            if href.startswith('#') or href.startswith('javascript:'):
                continue
            
            full_url = urljoin(base_domain, href) if not href.startswith('http') else href
            
            if urlparse(full_url).netloc != urlparse(base_domain).netloc:
                continue
            
            if is_job_related_url(full_url, link_text):
                job_links.append({'url': full_url, 'text': link_text})
        
        results = []
        for job_link in job_links[:3]:
            result = crawl_page(
                job_link['url'],
                base_domain,
                current_depth + 1,
                visited_urls.copy(),
                job_link['text']
            )
            if result:
                results.append(result)
        
        if results:
            best_result = results[0]
            content = extract_targeted_content(soup)
            best_result['content_for_gemini'] = content
            return best_result
        
        if current_depth == 0:
            return None
        
        content = extract_targeted_content(soup)
        return {
            'title': parent_title,
            'link': url,
            'content_for_gemini': content,
            'depth': current_depth
        }
        
    except Exception as e:
        print(f"Crawl error at depth {current_depth} for {url}: {type(e).__name__}: {e}")
        return None

def scrape_freejobalert_deep() -> List[Dict[str, Any]]:
    jobs = []
    base_urls = ['https://www.freejobalert.com/', 'https://freejobalert.com/']
    
    for base_url in base_urls:
        try:
            response = requests.get(base_url, impersonate="chrome", timeout=15)
            polite_delay()
            
            print(f'freejobalert deep ({base_url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_links = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                
                if href and text and len(text) >= 10:
                    full_url = href if href.startswith('http') else urljoin(base_url, href)
                    if is_job_related_url(full_url, text):
                        job_links.append({'url': full_url, 'text': text})
            
            for tr in soup.find_all('tr'):
                row_text = tr.get_text()
                if any(k in row_text.lower() for k in ['recruitment', 'vacancy', 'notification']):
                    for link in tr.find_all('a', href=True):
                        title = link.get_text(strip=True)
                        if title and len(title) >= 10:
                            href = link['href']
                            full_url = href if href.startswith('http') else urljoin(base_url, href)
                            job_links.append({'url': full_url, 'text': title})
            
            for job_link in job_links[:10]:
                result = crawl_page(
                    job_link['url'],
                    base_url,
                    current_depth=1,
                    visited_urls=set(),
                    parent_title=job_link['text']
                )
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
            print(f'freejobalert deep error: {type(e).__name__}: {e}')
    
    return jobs

def scrape_sarkari_result_deep() -> List[Dict[str, Any]]:
    jobs = []
    base_urls = ['https://www.sarkariresult.com/latestjob/']
    
    for base_url in base_urls:
        try:
            response = requests.get(base_url, impersonate="chrome", timeout=15)
            polite_delay()
            
            print(f'sarkariresult deep ({base_url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_links = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                
                if href and text and len(text) >= 10:
                    full_url = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                    if is_job_related_url(full_url, text):
                        job_links.append({'url': full_url, 'text': text})
            
            for job_link in job_links[:10]:
                result = crawl_page(
                    job_link['url'],
                    base_url,
                    current_depth=1,
                    visited_urls=set(),
                    parent_title=job_link['text']
                )
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
            print(f'sarkariresult deep error: {type(e).__name__}: {e}')
    
    return jobs

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_jobs:
        return []
    
    processed_jobs = []
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    system_instruction = (
        "You are an expert at extracting structured information from Indian government job recruitment notices. "
        "Given the extracted table and article content, extract:\n"
        "1. total_vacancies: Look explicitly for fields like 'Total Vacancy', 'Total Posts', or numbers in table cells (e.g., '1400+'). "
        "If a breakdown is provided (e.g., 'Category-wise: 100 UR, 50 OBC, ...'), sum them or take the total if explicitly stated. "
        "Do NOT default to 'Not specified' if the text contains any numeric vacancy information.\n"
        "2. official_apply_link: Locate and extract the actual government official website domain or registration link. "
        "Look for links containing '.gov.in', '.nic.in', or text labeled 'Official Website Link', 'Apply Online', 'Registration Link', etc.\n"
        "Return JSON with exactly: 'total_vacancies' (string) and 'official_apply_link' (string)."
    )
    
    for job in raw_jobs:
        org = normalize_organization(job.get('title', ''))
        total_vacancies = 'Not specified'
        official_apply_link = job.get('link', '')
        
        try:
            prompt = f"{system_instruction}\n\nJob Title: {job.get('title', '')}\n\nExtracted Content:\n{job.get('content_for_gemini', '')}"
            
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            start = result_text.find('{')
            end = result_text.rfind('}')
            if start != -1 and end != -1 and start < end:
                json_str = result_text[start:end+1]
                data = json.loads(json_str)
                total_vacancies = data.get('total_vacancies', 'Not specified')
                official_apply_link = data.get('official_apply_link', job.get('link', ''))
                if not isinstance(official_apply_link, str):
                    official_apply_link = str(official_apply_link)
                    
        except Exception as e:
            print(f"Gemini error for {job.get('title')}: {e}")
        
        processed_jobs.append({
            'title': job.get('title', ''),
            'organization': org,
            'total_vacancies': total_vacancies,
            'start_date': None,
            'last_date': '2026-12-31',
            'fee_details': 'As per official notification',
            'eligibility': 'Not specified',
            'official_apply_link': official_apply_link
        })
    
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
    print('Starting Deep Crawler Sarkari Jobs pipeline...')
    
    all_jobs = []
    
    print('Scraping FreeJobAlert (deep mode)...')
    all_jobs.extend(scrape_freejobalert_deep())
    
    print('Scraping SarkariResult (deep mode)...')
    all_jobs.extend(scrape_sarkari_result_deep())
    
    total_scraped = len(all_jobs)
    print(f'Total scraped: {total_scraped} job pages')
    
    if total_scraped == 0:
        print('No jobs scraped - adding test connection job')
        all_jobs.append({
            'title': f'Test Connection Job - DeepCrawler - {int(time.time())}',
            'organization': 'System Test',
            'total_vacancies': '1',
            'start_date': None,
            'last_date': '2026-12-31',
            'fee_details': 'Free',
            'eligibility': 'Test',
            'official_apply_link': 'https://example.com',
            'content_for_gemini': ''
        })
    
    processed_jobs = process_with_gemini(all_jobs)
    
    if not processed_jobs:
        print('No jobs processed - exiting')
        return
    
    inserted_count = sum(1 for job in processed_jobs if insert_job(job))
    deleted_count = cleanup_expired_jobs()
    
    print(f'Pipeline complete. Inserted: {inserted_count}, Deleted expired: {deleted_count}')

if __name__ == '__main__':
    main()