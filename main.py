from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import requests
import asyncio
import string
import random
import json
import time
import re

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
import undetected_chromedriver as uc

from curl_cffi.requests import Response
from curl_cffi.requests import Session
from colorama import Fore, init
from secmail import Client
import aiofiles

init(autoreset=True)

# constants

@dataclass
class EmailMessage:
    """Represents an email message."""
    id: int
    from_address: str
    subject: str
    html_body: str

@dataclass
class AccountData:
    """Represents account data for OpenRouter."""
    api_key: str
    api_key_name: str
    email: str
    password: str

    def to_dict(self) -> dict:
        """Converts the account data to a dictionary."""
        return {
            "key": {"api-key": self.api_key, "name": self.api_key_name},
            "email": self.email,
            "password": self.password
        }

class OpenRouterSignup:
    """Handles the signup process for OpenRouter."""
    CLERK_VERSION = "5.27.0"
    BASE_URL = "https://clerk.openrouter.ai/v1/client"
    
    def __init__(self, proxy_url: Optional[str] = None) -> None:
        """Initializes the OpenRouterSignup class."""
        self.session = Session(impersonate="chrome107", cookies=None, proxy=proxy_url)
        self.api_key_regex = r'"key":"(sk-[^"]+)"'
        self.cookies: List[Dict[str, Any]] = []
        self.signup_id: Optional[str] = None
        self.email_client = Client()
        self.email_address: str = ""
        self.api_key_name: str = ""
        self.password: str = ""
        self.jwt = None
        
    async def generate_email(self, domain: str = None) -> str:
        """Generates a random email address."""
        self.email_address = self.email_client.random_email(amount=1, domain=domain)[0]
        print(f"{Fore.CYAN}(!) Created email: {self.email_address}")
        return self.email_address
        
    async def bypass_protection(self) -> None:
        """Bypasses initial protection and fetches cookies."""
        self.session.get("https://openrouter.ai/")
        self.session.get(f"{self.BASE_URL}?_clerk_js_version={self.CLERK_VERSION}")
        self.cookies = dict(self.session.cookies)
        print(f"{Fore.YELLOW}(!) Bypassed protection and fetched cookies")
        
    async def start_signup(self, password: str) -> bool:
        """Starts the signup process with the provided email and password."""
        data = {
            'email_address': self.email_address,
            'password': password,
        }
        
        response = self.session.post(
            f'{self.BASE_URL}/sign_ups',
            params={'_clerk_js_version': self.CLERK_VERSION},
            data=data
        )
        
        self.signup_id = response.json()['response']['id']
        self.cookies = dict(self.session.cookies)
        self.password = password
        print(f"{Fore.GREEN}(!) Started signup for email: {self.email_address}")
        return True
        
    async def request_verification(self) -> Response:
        """Requests email verification."""
        data = {
            'strategy': 'email_link',
            'redirect_url': 'https://accounts.openrouter.ai/sign-up#/verify?sign_up_force_redirect_url=https%3A%2F%2Fopenrouter.ai%2F%3F',
        }
        
        response = self.session.post(
            f'{self.BASE_URL}/sign_ups/{self.signup_id}/prepare_verification',
            params={'_clerk_js_version': self.CLERK_VERSION},
            data=data
        )
        
        self.cookies = dict(self.session.cookies)
        print(f"{Fore.MAGENTA}(!) Requested email verification")
        return response
        
    async def wait_for_verification_email(self, timeout: int = 60) -> Optional[str]:
        """Waits for the verification email and extracts the verification link."""
        start_time = time.time()
        print(f"{Fore.CYAN}(!) Waiting for verification email...")
        while time.time() - start_time < timeout:
            inbox = self.email_client.get_inbox(self.email_address)
            
            for message in inbox:
                if "openrouter" in message.from_address.lower():
                    email_content = self.email_client.get_message(self.email_address, message.id)
                    url_match = re.search(r'https://[^\s]+', email_content.html_body).group().replace("amp;", "")[:-1]
                    if url_match:
                        print(f"{Fore.GREEN}(!) Got verification link: {url_match}")
                        return url_match
            
            await asyncio.sleep(5)
        return None

    async def launch_selenium(self, verify_url: str, headless: bool = True) -> None:
        """Launches Selenium to complete the verification process."""
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        
        if headless:
            options.add_argument("--headless")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")
        
        driver = uc.Chrome(
            options=options,
            suppress_welcome=True,
            use_subprocess=True,
            version_main=130
        )
        
        driver.get("https://openrouter.ai")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        if isinstance(self.cookies, dict):
            cookies_list = [
                {
                    'name': name,
                    'value': value,
                    'domain': '.openrouter.ai'
                }
                for name, value in self.cookies.items()
            ]
        else:
            cookies_list = self.cookies

        for cookie in cookies_list:
            if 'name' not in cookie or 'value' not in cookie:
                continue
                
            if 'domain' not in cookie:
                cookie['domain'] = '.openrouter.ai'
                
            clean_cookie = {
                k: v for k, v in cookie.items()
                if k in ['name', 'value', 'domain', 'path', 'secure', 'expiry']
            }
            
            driver.add_cookie(clean_cookie)

        driver.get(verify_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        await asyncio.sleep(4)
        driver.quit()
        
        await self.get_jwt()
    
    async def get_jwt(self) -> str:
        """Retrieves the JWT token."""
        data = {
            'identifier': self.email_address,
        }

        response = self.session.post(
            f'https://clerk.openrouter.ai/v1/client/sign_ins?_clerk_js_version={self.CLERK_VERSION}',
            data=data,
        )
        data = response.json()
        
        if data['response']['status'] == "needs_first_factor":
            response = self.session.post(
                f'https://clerk.openrouter.ai/v1/client/sign_ins/{data["response"]["id"]}/attempt_first_factor',
                params={"_clerk_js_version": self.CLERK_VERSION},
                data={
                    "strategy": "password",
                    "password": self.password    
                }
            )
            data = response.json()
            
            jwt_token = data['client']['sessions'][0]['last_active_token']['jwt']
            self.jwt = jwt_token
            print(f"{Fore.GREEN}(!) JWT retrieved successfully JWT: {jwt_token}")
                            
    async def generate_api_key(self) -> str:
        """Generates an API key."""
        cookies = {'__session': self.jwt, '__session_NO6jtgZM': self.jwt}
        self.api_key_name = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        data = f'[{{"name":"{self.api_key_name}","limit":null}}]'

        response = requests.post('https://openrouter.ai/settings/keys', cookies=cookies, data=data, headers={'next-action': 'e20f1f45c9c350f4bc59c480970318141293b673',})
        # why the fuck does self.session.post raise an error?

        api_key: str = re.search(self.api_key_regex, response.text).group(1)
                
        print(f"{Fore.GREEN}(!) API key generated! API key: {api_key}")
        return api_key

async def save_account_data(account_data: AccountData) -> None:
    """Saves account data to a JSON file."""
    async with aiofiles.open('accounts.json', 'a+') as f:
        await f.seek(0)
        content = await f.read()
        
        try:
            data = json.loads(content) if content else []
        except json.JSONDecodeError:
            data = []
            
        data.append(account_data.to_dict())
        await f.seek(0)
        await f.truncate()
        await f.write(json.dumps(data, indent=4))

async def create_account(proxy_url: Optional[str] = None) -> Optional[AccountData]:
    """Creates an OpenRouter account."""
    signup = OpenRouterSignup(proxy_url=proxy_url)
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    
    try:
        await signup.generate_email()
        await signup.bypass_protection()
        
        if await signup.start_signup(password):
            await signup.request_verification()
            verify_url = await signup.wait_for_verification_email()
            
            if verify_url:
                await signup.launch_selenium(verify_url)
                api_key = await signup.generate_api_key()
                return AccountData(api_key=api_key, email=signup.email_address, password=password, api_key_name=signup.api_key_name)
            
    except Exception as e:
        print(f"{Fore.RED}(!) Error creating account: {str(e)}")
    
    return None

async def main() -> None:
    """Main function to create accounts in a loop."""
    proxy_url: Optional[str] = None  # replace with your proxy url if you have one, else use a vpn dont use your ips or you will get banned by openrouter.
    while True:
        account_data = await create_account(proxy_url=proxy_url)
        if account_data:
            await save_account_data(account_data)
    
if __name__ == "__main__":
    asyncio.run(main()) # threads / mutiple tasks will break driver