import time
import random
import string
import re

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from emailnator import Emailnator

class Log:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    @staticmethod
    def info(msg):
        print(f"{Log.OKBLUE}[INFO]{Log.ENDC} {msg}")
    @staticmethod
    def success(msg):
        print(f"{Log.OKGREEN}[SUCCESS]{Log.ENDC} {msg}")
    @staticmethod
    def warn(msg):
        print(f"{Log.WARNING}[WARN]{Log.ENDC} {msg}")
    @staticmethod
    def error(msg):
        print(f"{Log.FAIL}[ERROR]{Log.ENDC} {msg}")


def generate_strong_password(length=16):
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choices(chars, k=length))

def get_temp_email():
    emailnator = Emailnator()
    email_data = emailnator.generate_email(options=["dotGmail"])
    email = email_data["email"][0]
    Log.info(f"Generated temp email: {email}")
    return email, emailnator

def check_turnstile(driver):
    """
    This doesn't work at all, to lazy to fix
    """
    try: 
        page_source = driver.page_source.lower()
        if 'verify you are human' in page_source:
            Log.warn("Cloudflare/Turnstile detected! Please solve the challenge in the browser window.")
            input("Press Enter after you have solved the challenge...")
            return True
    except Exception as e:
        Log.warn(f"Error checking for Turnstile: {e}")
    return False

def wait_for_email_verification(emailnator, email, driver):
    Log.info("Waiting for sign-up email...")
    signup_email = None
    for _ in range(7):
        emails = emailnator.inbox(email)
        messages = emails.get("messageData", [])
        for msg in messages:
            if "openrouter" in msg.get("from", "").lower() or "openrouter" in msg.get("subject", "").lower():
                signup_email = msg
                break
        if signup_email:
            break
        check_turnstile(driver)
        time.sleep(1)
    else:
        Log.error("No OpenRouter sign-up email found in time, probably Cloudflare turnstile or already in use email was selected")
        raise ValueError()
    
    message_id = signup_email["messageID"]
    email_content = emailnator.get_message(email, message_id)
    url_match = re.search(r'https://[^\s"<>]*openrouter[^\s"<>]*', str(email_content))
    if url_match:
        signup_url = url_match.group(0).replace('amp;', '')
        Log.info(f"Found sign-up URL: {signup_url}")
        driver.get(signup_url)
    else:
        print(email_content)
        Log.error("No sign-up URL found in email.")

def sign_up(driver, wait, email, password):
    driver.get("https://openrouter.ai/")
    sign_in_button = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, '[component="SignInButton"]'))
    )
    sign_in_button.click()
    sign_up_link = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[href*="sign-up"]'))
    )
    sign_up_link.click()
    email_input = wait.until(
        EC.element_to_be_clickable((By.ID, 'emailAddress-field'))
    )
    email_input.clear()
    email_input.send_keys(email)
    password_input = wait.until(
        EC.element_to_be_clickable((By.ID, 'password-field'))
    )
    password_input.clear()
    password_input.send_keys(password)
    checkbox = wait.until(
        EC.element_to_be_clickable((By.ID, 'legalAccepted-field'))
    )
    if not checkbox.is_selected():
        checkbox.click()
    continue_button = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-localization-key="formButtonPrimary"]'))
    )
    continue_button.click()
    Log.success(f"Signed up with {email}")

def create_api_key(driver, wait, key_name):
    avatar_button = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[id^="radix-"][id*="-trigger-"]'))
    )
    avatar_button.click()
    keys_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//button[contains(., "Keys")]'))
    )
    keys_button.click()
    create_api_key_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//button[contains(., "Create API Key")]'))
    )
    create_api_key_button.click()
    api_key_name_input = wait.until(
        EC.element_to_be_clickable((By.ID, 'name'))
    )
    api_key_name_input.clear()
    api_key_name_input.send_keys(key_name)
    create_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//button[normalize-space(text())="Create" and not(@disabled)]'))
    )
    create_button.click()
    api_key_code = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, 'code.my-4'))
    )
    api_key_value = api_key_code.text
    with open('api_key.txt', 'a') as f:
        f.write(api_key_value + '\n')
    Log.success(f"Created new API key: {Log.BOLD}{api_key_value}{Log.ENDC}")
    return api_key_value

def main():
    try:
        num_keys = int(input("How many API keys do you want to create? "))
    except Exception:
        Log.error("Invalid input. Exiting.")
        return
    i = 0
    while i < num_keys:
        try:
            Log.info(f"Starting process for API key {i+1}/{num_keys}")
            options = uc.ChromeOptions()
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-blink-features=AutomationControlled")
            driver = uc.Chrome(options=options)
            wait = WebDriverWait(driver, 10)
            email, emailnator = get_temp_email()
            password = generate_strong_password()
            sign_up(driver, wait, email, password)
            wait_for_email_verification(emailnator, email, driver)
            _api_key = create_api_key(driver, wait, f"Key {i+1}")
            driver.quit()
            Log.info(f"Finished process for API key {i+1}/{num_keys}\n")
            i += 1
        except Exception as e:
            Log.error(f"Error during process for API key {i+1}: {e}")
            try:
                driver.quit()
            except:
                pass
            Log.info("Retrying...")
            
    Log.success(f"All done! API keys saved to api_key.txt")

if __name__ == "__main__":
    main()
