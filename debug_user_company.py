"""
Debug script to understand user and company relationships
"""

import requests
import json

class DebugTester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url.rstrip('/')
        self.token = None

    def make_request(self, method: str, endpoint: str, data=None):
        """Make HTTP request with authentication"""
        url = f"{self.base_url}/api{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=30)
            
            response_data = response.json() if response.content and response.headers.get('content-type', '').startswith('application/json') else response.text
            return response.status_code, response_data
        except Exception as e:
            return 0, str(e)

    def debug_user_company_relationship(self):
        """Debug the user-company relationship"""
        print("🔐 Logging in...")
        
        login_data = {
            "email": "aminderpro@gmail.com",
            "password": "Admin@123!"
        }
        
        status, response = self.make_request('POST', '/auth/login', data=login_data)
        print(f"Login Status: {status}")
        
        if status == 200 and isinstance(response, dict):
            if 'access_token' in response:
                self.token = response['access_token']
                user_data = response.get('user', {})
                print(f"User ID: {user_data.get('id')}")
                print(f"User Role: {user_data.get('role')}")
                print(f"User Email: {user_data.get('email')}")
                print(f"Company ID: {user_data.get('company_id', 'N/A')}")
                print(f"Fleet Owner ID: {user_data.get('fleet_owner_id', 'N/A')}")
            elif 'token' in response:
                self.token = response['token']
                user_data = response.get('user', {})
                print(f"User ID: {user_data.get('id')}")
                print(f"User Role: {user_data.get('role')}")
                print(f"User Email: {user_data.get('email')}")
                print(f"Company ID: {user_data.get('company_id', 'N/A')}")
                print(f"Fleet Owner ID: {user_data.get('fleet_owner_id', 'N/A')}")
        
        print("\n🏢 Testing /companies/current...")
        status, response = self.make_request('GET', '/companies/current')
        print(f"Companies Current Status: {status}")
        print(f"Response: {response}")
        
        print("\n🏢 Testing /companies/my...")
        status, response = self.make_request('GET', '/companies/my')
        print(f"Companies My Status: {status}")
        print(f"Response: {response}")
        
        print("\n📋 Testing carrier profile...")
        status, response = self.make_request('GET', '/carrier-profiles')
        print(f"Carrier Profile Status: {status}")
        if status == 200:
            print(f"Profile Company ID: {response.get('company_id', 'N/A')}")
            print(f"Profile User ID: {response.get('user_id', 'N/A')}")

def main():
    debug = DebugTester()
    debug.debug_user_company_relationship()

if __name__ == "__main__":
    main()