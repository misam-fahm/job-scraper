from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QGroupBox, QAbstractItemView, QDialog, QMessageBox
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, pyqtSlot, QThread, pyqtSignal
import sys
import requests
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import webbrowser

class ScraperThread(QThread):
    update_table = pyqtSignal(dict)
    finished = pyqtSignal()

    def _init_(self, job_title, location, desired_jobs, days_filter=None):
        super()._init_()
        self.job_title = job_title
        self.location = location
        self.desired_jobs = desired_jobs
        self.days_filter = days_filter
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        url = f"https://www.naukri.com/{self.job_title}-jobs-in-{self.location}"
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        scraped_jobs = 0
        seen_jobs = set()
        job_listings = []

        while self.is_running and (self.desired_jobs == float('inf') or scraped_jobs < self.desired_jobs):
            job_cards = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, '//div[contains(@class,"srp-jobtuple-wrapper")]'))
            )
            if not job_cards:
                break

            for job in job_cards:
                if not self.is_running or (self.desired_jobs != float('inf') and scraped_jobs >= self.desired_jobs):
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

                    if self.days_filter:
                        if not self.check_days_filter(posted, self.days_filter):
                            continue

                    job_listings.append(job_data)
                    self.update_table.emit(job_data)
                    scraped_jobs += 1

                except Exception as e:
                    print(f"Error processing job: {str(e)}")
                    continue

            if self.is_running and (self.desired_jobs == float('inf') or scraped_jobs < self.desired_jobs):
                try:
                    next_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, '//*[@id="lastCompMark"]/a[2]'))
                    )
                    driver.execute_script("arguments[0].click();", next_button)
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.XPATH, '//div[contains(@class,"srp-jobtuple-wrapper")]'))
                    )
                except:
                    break

        existing_jobs = []
        if os.path.exists("job_listings.json"):
            with open("job_listings.json", "r", encoding="utf-8") as file:
                try:
                    existing_jobs = json.load(file)
                except json.JSONDecodeError:
                    print("Error: JSON file is corrupted. Starting with an empty list.")
                    existing_jobs = []
        existing_jobs.extend(job_listings)
        with open("job_listings.json", "w", encoding="utf-8") as file:
            json.dump(existing_jobs, file, indent=4, ensure_ascii=False)

        driver.quit()
        self.finished.emit()

    def check_days_filter(self, posted_text, days):
        if "Few Hours Ago" in posted_text:
            return True
        if "Day Ago" in posted_text:
            days_ago = int(posted_text.split()[0])
            return days_ago <= days
        if "Days Ago" in posted_text:
            days_ago = int(posted_text.split()[0])
            return days_ago <= days
        return False

class JobDetailDialog(QDialog):
    def _init_(self, job_data):
        super()._init_()
        self.job_data = job_data
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Job Details")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout()

        title_label = QLabel(f"Job Title: {self.job_data['job_title']}")
        title_label.setFont(QFont('Arial', 14, QFont.Bold))
        layout.addWidget(title_label)

        company_label = QLabel(f"Company: {self.job_data['company']}")
        layout.addWidget(company_label)

        experience_label = QLabel(f"Experience: {self.job_data['experience']}")
        layout.addWidget(experience_label)

        salary_label = QLabel(f"Salary: {self.job_data['salary']}")
        layout.addWidget(salary_label)

        location_label = QLabel(f"Location: {self.job_data['location']}")
        layout.addWidget(location_label)

        posted_label = QLabel(f"Posted: {self.job_data['posted']}")
        layout.addWidget(posted_label)

        opening_date_label = QLabel(f"Opening Date: {self.job_data['opening_date']}")
        layout.addWidget(opening_date_label)

        link_button = QPushButton("Click Here")
        link_button.clicked.connect(self.open_job_link)
        link_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 15px;
                font-size: 14px;
                cursor: pointer;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        layout.addWidget(link_button)

        email_label = QLabel(f"Email: {self.job_data['email']}")
        layout.addWidget(email_label)

        self.setLayout(layout)

    def open_job_link(self):
        webbrowser.open(self.job_data['job_link'])

class JobScraperApp(QWidget):
    def _init_(self):
        super()._init_()
        self.job_links = []
        self.job_listings = []
        self.scraper_thread = None
        self.days_filter = None
        self.initUI()

    @pyqtSlot()
    def open_job_link(self):
        button = self.sender()
        if button:
            row = self.output_table.indexAt(button.pos()).row()
            if row < len(self.job_links):
                webbrowser.open(self.job_links[row])

    @pyqtSlot()
    def show_job_detail(self):
        button = self.sender()
        if button:
            row = self.output_table.indexAt(button.pos()).row()
            if row < len(self.job_listings):
                job_data = self.job_listings[row]
                detail_dialog = JobDetailDialog(job_data)
                detail_dialog.exec_()

    def start_scraping(self):
        job_title = self.input_job.text().strip().replace(" ", "-")
        location = self.input_location.text().strip().replace(" ", "-")

        try:
            desired_jobs = int(self.input_count.text().strip())
            if desired_jobs == 0:
                desired_jobs = float('inf')
        except ValueError:
            desired_jobs = float('inf')

        if not job_title or not location:
            QMessageBox.warning(self, "Input Error", "Please enter both job title and location.")
            return

        self.output_table.setRowCount(0)
        self.job_links.clear()
        self.job_listings.clear()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.scraper_thread = ScraperThread(job_title, location, desired_jobs, self.days_filter)
        self.scraper_thread.update_table.connect(self.update_table)
        self.scraper_thread.finished.connect(self.scraping_finished)
        self.scraper_thread.start()

    def stop_scraping(self):
        if self.scraper_thread and self.scraper_thread.isRunning():
            self.scraper_thread.stop()

    def update_table(self, job_data):
        row = self.output_table.rowCount()
        self.output_table.insertRow(row)
        self.output_table.setItem(row, 0, QTableWidgetItem(job_data["job_title"]))
        self.output_table.setItem(row, 1, QTableWidgetItem(job_data["company"]))
        self.output_table.setItem(row, 2, QTableWidgetItem(job_data["experience"]))
        self.output_table.setItem(row, 3, QTableWidgetItem(job_data["salary"]))
        self.output_table.setItem(row, 4, QTableWidgetItem(job_data["location"]))
        self.output_table.setItem(row, 5, QTableWidgetItem(job_data["posted"]))
        self.output_table.setItem(row, 6, QTableWidgetItem(job_data["opening_date"]))

        view_detail_btn = QPushButton("View Details")
        view_detail_btn.clicked.connect(self.show_job_detail)
        view_detail_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
                cursor: pointer;
            }
            QPushButton:hover {
                background-color: #3a80d2;
            }
        """)
        self.output_table.setCellWidget(row, 7, view_detail_btn)
        self.output_table.setItem(row, 8, QTableWidgetItem(job_data["email"]))

        self.job_links.append(job_data["job_link"])
        self.job_listings.append(job_data)
        self.output_table.resizeColumnsToContents()

    def scraping_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        QMessageBox.information(self, "Scraping Complete", "Job scraping completed successfully!")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.start_scraping()

    def set_days_filter(self, days):
        self.days_filter = days

    def initUI(self):
        self.setWindowTitle("Job Search - Talentin")
        self.setMinimumSize(1000, 700)

        # CSS Styles
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                font-family: Arial, sans-serif;
            }
            QLabel {
                color: #333;
                font-size: 12px;
            }
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 15px;
                font-size: 16px;
                height: 20px;
                width: 100%;
            }
            QLineEdit:focus {
                border-color: #4a90e2;
                background-color: white;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 12px 20px;
                font-size: 16px;
                cursor: pointer;
            }
            QPushButton:hover {
                background-color: #3a80d2;
            }
            QPushButton:pressed {
                background-color: #2a60b2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QTableWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #e6f2ff;
            }
            QTableWidget::item {
                padding: 10px;
            }
            QTableWidget::item:hover {
                background-color: #f0f8ff;
            }
            QTableWidget::item:selected {
                background-color: #e6f2ff;
            }
            QTableWidget QHeaderView::section {
                background-color: #f0f0f0;
                padding: 10px;
                border: 1px solid #ccc;
            }
            QGroupBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 15px;
            }
            QLabel#title {
                color: #4a90e2;
                font-size: 66px;
                font-weight: bold;
            }
        """)

        # Title
        self.label_logo = QLabel("Talentin Job Search")
        self.label_logo.setObjectName("title")
        self.label_logo.setAlignment(Qt.AlignCenter)
        title_layout = QHBoxLayout()
        title_layout.addStretch()
        title_layout.addWidget(self.label_logo)
        title_layout.addStretch()

        # Input Group
        self.input_container = QGroupBox(self)
        input_layout = QVBoxLayout()
        self.label_job = QLabel("Job Title:")
        self.input_job = QLineEdit()
        self.label_location = QLabel("Location:")
        self.input_location = QLineEdit()
        self.label_count = QLabel("Number of Jobs to fetch (optional):")
        self.input_count = QLineEdit()

        input_layout.addWidget(self.label_job)
        input_layout.addWidget(self.input_job)
        input_layout.addWidget(self.label_location)
        input_layout.addWidget(self.input_location)
        input_layout.addWidget(self.label_count)
        input_layout.addWidget(self.input_count)
        self.input_container.setLayout(input_layout)

        input_box_layout = QHBoxLayout()
        input_box_layout.addStretch()
        input_box_layout.addWidget(self.input_container)
        input_box_layout.addStretch()

        # Filter Buttons
        filter_layout = QHBoxLayout()
        filter_layout.addStretch()
        self.filter_7_days = QPushButton("Last 7 Days")
        self.filter_7_days.clicked.connect(lambda: self.set_days_filter(7))
        self.filter_7_days.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 15px;
                font-size: 14px;
                cursor: pointer;
            }
            QPushButton:hover {
                background-color: #3a80d2;
            }
            QPushButton:pressed {
                background-color: #2a60b2;
            }
        """)
        self.filter_15_days = QPushButton("Last 15 Days")
        self.filter_15_days.clicked.connect(lambda: self.set_days_filter(15))
        self.filter_15_days.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 15px;
                font-size: 14px;
                cursor: pointer;
            }
            QPushButton:hover {
                background-color: #3a80d2;
            }
            QPushButton:pressed {
                background-color: #2a60b2;
            }
        """)
        self.filter_30_days = QPushButton("Last 30 Days")
        self.filter_30_days.clicked.connect(lambda: self.set_days_filter(30))
        self.filter_30_days.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 15px;
                font-size: 14px;
                cursor: pointer;
            }
            QPushButton:hover {
                background-color: #3a80d2;
            }
            QPushButton:pressed {
                background-color: #2a60b2;
            }
        """)
        filter_layout.addWidget(self.filter_7_days)
        filter_layout.addWidget(self.filter_15_days)
        filter_layout.addWidget(self.filter_30_days)
        filter_layout.addStretch()

        # Buttons
        self.start_button = QPushButton("Search Jobs")
        self.start_button.clicked.connect(self.start_scraping)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 12px 20px;
                font-size: 16px;
                cursor: pointer;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3a803a;
            }
        """)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_scraping)
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 12px 20px;
                font-size: 16px;
                cursor: pointer;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #c62828;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch()

        # Table
        self.output_table = QTableWidget()
        self.output_table.setColumnCount(9)
        self.output_table.setHorizontalHeaderLabels([
            "Job Title", "Company", "Experience", "Salary", "Location", "Posted", "Opening",
            "Actions", "Email"
        ])
        self.output_table.horizontalHeader().setStretchLastSection(True)
        self.output_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.output_table.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Main Layout
        layout = QVBoxLayout()
        layout.addLayout(title_layout)
        layout.addLayout(input_box_layout)
        layout.addLayout(filter_layout)
        layout.addLayout(button_layout)
        layout.addWidget(self.output_table)
        self.setLayout(layout)

if _name_ == "_main_":
    app = QApplication(sys.argv)
    window = JobScraperApp()
    window.show()
    sys.exit(app.exec_())