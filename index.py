from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import os
import re
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

def get_chrome_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36")
    
    service = Service('/usr/local/bin/chromedriver')
    return webdriver.Chrome(service=service, options=options)

def scrape_jobs(job_title, location, desired_jobs=float('inf'), days_filter=None):
    """Generator function to scrape jobs and yield results as they're found"""
    url = f"https://www.naukri.com/{job_title}-jobs-in-{location}"
    driver = get_chrome_driver()
    driver.get(url)

    scraped_jobs = 0
    seen_jobs = set()
    
    try:
        while desired_jobs == float('inf') or scraped_jobs < desired_jobs:
            job_cards = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, '//div[contains(@class,"srp-jobtuple-wrapper")]'))
            )
            if not job_cards:
                break

            for job in job_cards:
                if desired_jobs != float('inf') and scraped_jobs >= desired_jobs:
                    break
                try:
                    title_element = job.find_element(By.XPATH, './/a[contains(@class,"title")]')
                    job_title = title_element.text.strip()
                    job_link = title_element.get_attribute('href')

                    if job_link in seen_jobs:
                        continue
                    seen_jobs.add(job_link)

                    company_name = job.find_element(By.XPATH, './/a[contains(@class,"comp-name")]').text.strip() if job.find_elements(By.XPATH, './/a[contains(@class,"comp-name")]') else "Not Provided"
                    experience = job.find_element(By.XPATH, './/span[contains(@title,"Yrs")]').text.strip() if job.find_elements(By.XPATH, './/span[contains(@title,"Yrs")]') else "Not Provided"
                    salary = job.find_element(By.XPATH, './/span[contains(@title,"Lacs")]').text.strip() if job.find_elements(By.XPATH, './/span[contains(@title,"Lacs")]') else "Not Disclosed"
                    location = job.find_element(By.XPATH, './/span[contains(@class,"location")]').text.strip() if job.find_elements(By.XPATH, './/span[contains(@class,"location")]') else "Not Provided"
                    posted = job.find_element(By.XPATH, './/span[contains(text(), "Ago")]').text.strip() if job.find_elements(By.XPATH, './/span[contains(text(), "Ago")]') else "Not Available"

                    opening_date = "Not Available"
                    driver.execute_script("window.open('');")
                    driver.switch_to.window(driver.window_handles[1])
                    driver.get(job_link)

                    try:
                        opening_date_element = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, '//*[@id="job_header"]/div[2]/div[1]/span[2]/span'))
                        )
                        opening_date = opening_date_element.text.strip()
                    except:
                        opening_date = "Not Available"

                    email = "Not Found"
                    page_source = driver.page_source
                    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
                    email_matches = re.findall(email_pattern, page_source)
                    if email_matches:
                        email = email_matches[0]

                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])

                    job_data = {
                        "job_title": job_title,
                        "company": company_name,
                        "experience": experience,
                        "salary": salary,
                        "location": location,
                        "posted": posted,
                        "opening_date": opening_date,
                        "job_link": job_link,
                        "email": email
                    }

                    if days_filter:
                        if not check_days_filter(posted, days_filter):
                            continue

                    # Save to file (optional)
                    save_job_to_file(job_data)
                    
                    # Yield the job data as it's found
                    yield json.dumps(job_data) + "\n"
                    scraped_jobs += 1

                except Exception as e:
                    print(f"Error processing job: {str(e)}")
                    continue

            # Try to go to next page if needed
            if desired_jobs == float('inf') or scraped_jobs < desired_jobs:
                try:
                    next_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, '//*[@id="lastCompMark"]/a[2]'))
                    )
                    driver.execute_script("arguments[0].click();", next_button)
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.XPATH, '//div[contains(@class,"srp-jobtuple-wrapper")]'))
                    )
                    # Sleep briefly to let page load
                    time.sleep(2)
                except:
                    break
    finally:
        driver.quit()

def check_days_filter(posted_text, days):
    """Check if the job posting is within the specified number of days"""
    if "Few Hours Ago" in posted_text:
        return True
    if "Day Ago" in posted_text:
        days_ago = int(posted_text.split()[0])
        return days_ago <= days
    if "Days Ago" in posted_text:
        days_ago = int(posted_text.split()[0])
        return days_ago <= days
    return False

def save_job_to_file(job_data):
    """Save job data to a JSON file"""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    json_file = os.path.join(data_dir, "job_listings.json")
    existing_jobs = []
    
    if os.path.exists(json_file):
        with open(json_file, "r", encoding="utf-8") as file:
            try:
                existing_jobs = json.load(file)
            except json.JSONDecodeError:
                print("Error: JSON file is corrupted. Starting with an empty list.")
                existing_jobs = []
    
    # Add the new job to the list
    existing_jobs.append(job_data)
    
    # Save the updated list back to the file
    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(existing_jobs, file, indent=4, ensure_ascii=False)

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "running",
        "message": "Job scraper API is operational",
        "endpoints": {
            "/api/jobs/search": "Search for jobs with parameters: job_title, location, count, days",
            "/api/jobs/list": "List all saved jobs"
        }
    })

@app.route('/api/jobs/search', methods=['GET'])
def search_jobs():
    """Streaming endpoint to search and return jobs"""
    job_title = request.args.get('job_title', '').strip().replace(" ", "-")
    location = request.args.get('location', '').strip().replace(" ", "-")
    
    try:
        count = int(request.args.get('count', '0'))
        if count == 0:
            count = float('inf')
    except ValueError:
        count = float('inf')
    
    days_filter = None
    if 'days' in request.args:
        try:
            days_filter = int(request.args.get('days'))
        except ValueError:
            pass
    
    if not job_title or not location:
        return jsonify({"error": "Please provide both job_title and location parameters"}), 400
    
    return Response(
        scrape_jobs(job_title, location, count, days_filter),
        mimetype='text/event-stream'
    )

@app.route('/api/jobs/list', methods=['GET'])
def list_jobs():
    """Return all previously saved jobs"""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    json_file = os.path.join(data_dir, "job_listings.json")
    
    if os.path.exists(json_file):
        with open(json_file, "r", encoding="utf-8") as file:
            try:
                jobs = json.load(file)
                return jsonify(jobs)
            except json.JSONDecodeError:
                return jsonify({"error": "Could not read job listings file"}), 500
    else:
        return jsonify([])

@app.route('/api/jobs/clear', methods=['POST'])
def clear_jobs():
    """Clear all saved jobs"""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    json_file = os.path.join(data_dir, "job_listings.json")
    
    if os.path.exists(json_file):
        os.remove(json_file)
    return jsonify({"message": "Job listings cleared successfully"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)