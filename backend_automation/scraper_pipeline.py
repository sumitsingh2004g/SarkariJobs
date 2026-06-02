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

import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)

MAX_DEPTH = 2
POLITE_DELAY_MIN = 2
POLITE_DELAY_MAX = 3

NAVBAR_SELECTOR_PATTERNS = [
    r'home', r'about', r'contact', r'privacy', r'terms', r'sitemap',
    r'facebook', r'twitter', r'instagram', r'linkedin', r'youtube',
    r'wp-content', r'wp-admin', r'rss', r'feed', r'sitemap\.xml'
]

def polite_delay():
    delay = random.uniform(POLITE_DELAY_MIN, POLITE_DELAY_MAX)
    time.sleep(delay)

def is_navbar_or_menu_link(soup: BeautifulSoup, link) -> bool:
    parent_classes = []
    parent = link.parent
    while parent and parent != soup:
        if parent.get('class'):
            parent_classes.extend(parent['class'])
        parent = parent.parent
    
    parent_texts = ' '.join(parent_classes).lower()
    for pattern in NAVBAR_SELECTOR_PATTERNS:
        if re.search(pattern, parent_texts):
            return True
    
    href = link.get('href', '')
    if re.search(r'(?:^/|^#)(home|about|contact|privacy|terms)', href, re.I):
        return True
    
    return False

def is_valid_job_detail_url(url: str, link_text: str) -> bool:
    if not url or not link_text:
        return False
    
    url_lower = url.lower()
    text_lower = link_text.lower()
    
    if any(re.search(p, url_lower) for p in NAVBAR_SELECTOR_PATTERNS):
        return False
    
    if '#' in url or 'javascript:' in url:
        return False
    
    if re.search(r'\.pdf$', url):
        return False
    
    job_pattern = r'\b(2024|2025|2026|2027|2028)\b'
    if not re.search(job_pattern, text_lower):
        if not re.search(r'\b(recruitment|vacancy|notification|online|apply)\b', text_lower):
            return False
    
    spam_patterns = ['freejobalert\.com', 'sarkari result', 'home', 'click here']
    if any(spam.lower() in text_lower for spam in spam_patterns):
        if len(text_lower) < 50:
            return False
    
    return True

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

def extract_vacancy_info(soup: BeautifulSoup) -> str:
    vacancy_texts = []
    
    for table in soup.find_all('table'):
        rows = []
        for tr in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if len(cells) >= 2:
                rows.append(' | '.join(cells))
        if rows:
            vacancy_texts.append('\n'.join(rows))
    
    if vacancy_texts:
        return '\n\n'.join(vacancy_texts[-3:])
    
    return ''

def extract_article_content(soup: BeautifulSoup) -> str:
    for tag in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav', 'aside']):
        tag.decompose()
    
    content_divs = soup.find_all('div', class_=re.compile(r'(content|entry|article|post|main)', re.I))
    if content_divs:
        return '\n'.join(d.get_text(separator=' ', strip=True) for d in content_divs[:2])
    
    paragraphs = []
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if len(text) > 30 and not any(x in text.lower() for x in ['click here', 'follow us', 'subscribe', 'disclaimer']):
            paragraphs.append(text)
    
    return '\n'.join(paragraphs[:15])

def crawl_page(
    url: str,
    base_domain: str,
    current_depth: int,
    visited_urls: set,
    link_text: str = ''
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
            content = extract_vacancy_info(soup) + '\n' + extract_article_content(soup)
            return {
                'title': link_text,
                'link': url,
                'content_for_gemini': content[:4000],
                'depth': current_depth
            }
        
        job_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True)
            
            if not text or len(text) < 15:
                continue
            
            if is_navbar_or_menu_link(soup, link):
                continue
            
            if not is_valid_job_detail_url(href, text):
                continue
            
            full_url = urljoin(base_domain, href) if not href.startswith('http') else href
            
            parsed_full = urlparse(full_url)
            parsed_base = urlparse(base_domain)
            if parsed_full.netloc != parsed_base.netloc:
                continue
            
            if full_url in visited_urls:
                continue
            
            job_links.append({'url': full_url, 'text': text})
        
        for job_link in job_links[:2]:
            result = crawl_page(
                job_link['url'],
                base_domain,
                current_depth + 1,
                visited_urls.copy(),
                job_link['text']
            )
            if result:
                return result
        
        return None
        
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
            
            print(f'freejobalert ({base_url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_links = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                
                if not text or len(text) < 15:
                    continue
                
                if is_navbar_or_menu_link(soup, link):
                    continue
                
                if not is_valid_job_detail_url(href, text):
                    continue
                
                full_url = href if href.startswith('http') else urljoin(base_url, href)
                job_links.append({'url': full_url, 'text': text})
            
            for tr in soup.find_all('tr'):
                row_text = tr.get_text(separator=' ', strip=True)
                if any(k in row_text.lower() for k in ['recruitment', 'vacancy', 'notification', '2024', '2025', '2026']):
                    for link in tr.find_all('a', href=True):
                        title = link.get_text(strip=True)
                        href = link['href']
                        if href and title and len(title) >= 15 and not is_navbar_or_menu_link(soup, link):
                            full_url = href if href.startswith('http') else urljoin(base_url, href)
                            if is_valid_job_detail_url(full_url, title):
                                job_links.append({'url': full_url, 'text': title})
            
            seen_urls = set()
            for job_link in job_links[:10]:
                if job_link['url'] in seen_urls:
                    continue
                seen_urls.add(job_link['url'])
                
                result = crawl_page(
                    job_link['url'],
                    base_url,
                    current_depth=1,
                    visited_urls=set(),
                    link_text=job_link['text']
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
            print(f'freejobalert error: {type(e).__name__}: {e}')
    
    return jobs

def scrape_sarkari_result_deep() -> List[Dict[str, Any]]:
    jobs = []
    base_urls = ['https://www.sarkariresult.com/latestjob/']
    
    for base_url in base_urls:
        try:
            response = requests.get(base_url, impersonate="chrome", timeout=15)
            polite_delay()
            
            print(f'sarkariresult ({base_url}): Status {response.status_code}')
            
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_links = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True)
                
                if not text or len(text) < 15:
                    continue
                
                if is_navbar_or_menu_link(soup, link):
                    continue
                
                if not is_valid_job_detail_url(href, text):
                    continue
                
                full_url = href if href.startswith('http') else f'https://sarkariresult.com{href}'
                job_links.append({'url': full_url, 'text': text})
            
            seen_urls = set()
            for job_link in job_links[:10]:
                if job_link['url'] in seen_urls:
                    continue
                seen_urls.add(job_link['url'])
                
                result = crawl_page(
                    job_link['url'],
                    base_url,
                    current_depth=1,
                    visited_urls=set(),
                    link_text=job_link['text']
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
            print(f'sarkariresult error: {type(e).__name__}: {e}')
    
    return jobs

def process_with_gemini(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_jobs:
        return []
    
    processed_jobs = []
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    system_instruction = (
        "Extract structured info from Indian govt job notices. Return JSON only.\n"
        "1. total_vacancies: Extract number from 'Total Vacancy', 'Total Posts', or table cells. "
        "Sum category-wise if needed. Return 'Not specified' only if no number found.\n"
        "2. official_apply_link: Extract gov.in/nic.in URLs or text labeled 'Apply Online', 'Official Website'.\n"
        "JSON keys: total_vacancies (string), official_apply_link (string)."
    )
    
    for job in raw_jobs:
        org = normalize_organization(job.get('title', ''))
        total_vacancies = 'Not specified'
        official_apply_link = job.get('link', '')
        
        try:
            prompt = f"{system_instruction}\n\nJob Title: {job.get('title', '')}\n\nContent:\n{job.get('content_for_gemini', '')}"
            
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
        print(f'Insert error: {type(e).__name__}: {e}')
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
    print('Starting Deep Crawler pipeline...')
    
    all_jobs = []
    
    print('Scraping FreeJobAlert...')
    all_jobs.extend(scrape_freejobalert_deep())
    
    print('Scraping SarkariResult...')
    all_jobs.extend(scrape_sarkari_result_deep())
    
    total_scraped = len(all_jobs)
    print(f'Total scraped: {total_scraped} job pages')
    
    if total_scraped == 0:
        print('No jobs scraped - adding test job')
        all_jobs.append({
            'title': f'Test Job - {int(time.time())}',
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