"""
Direct Carrier Profile Sync Test
Tests the sync functionality by manually updating database
"""

import requests
import json
import os
import pymongo
from datetime import datetime

class DirectSyncTester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.user_id = None
        self.company_id = None

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
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data, timeout=30)
            
            return response.status_code, response.json() if response.content else {}
        except Exception as e:
            return 0, str(e)

    def connect_to_db(self):
        """Connect to MongoDB directly"""
        try:
            mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
            client = pymongo.MongoClient(mongo_url)
            db = client.fleet_marketplace
            return db
        except Exception as e:
            print(f"Database connection failed: {e}")
            return None

    def test_sync_verification(self):
        """Test the sync functionality with direct database access"""
        print("🧪 Starting Direct Sync Verification Test")
        print("=" * 50)
        
        # 1. Login
        print("🔐 Logging in...")
        login_data = {
            "email": "aminderpro@gmail.com",
            "password": "Admin@123!"
        }
        
        status, response = self.make_request('POST', '/auth/login', data=login_data)
        if status != 200:
            print(f"❌ Login failed: {status}")
            return False
        
        self.token = response.get('access_token') or response.get('token')
        self.user_id = response.get('user', {}).get('id') or response.get('user_id')
        print(f"✅ Logged in, User ID: {self.user_id}")
        
        # 2. Get carrier profile
        print("📋 Getting carrier profile...")
        status, profile = self.make_request('GET', '/carrier-profiles')
        if status != 200:
            print(f"❌ Get profile failed: {status}")
            return False
        
        print(f"✅ Got profile: {profile.get('id')}")
        print(f"   Current company_id: {profile.get('company_id', 'None')}")
        
        # 3. Create company if needed
        print("🏗️ Creating company...")
        company_data = {
            "name": "Direct Sync Test Company",
            "company_type": "trucking",
            "address": "789 Direct Test Ave",
            "city": "Vancouver",
            "state": "BC",
            "zip_code": "V6B 1A1",
            "country": "CA",
            "mc_number": "MC-DIRECT123",
            "dot_number": "DOT987654"
        }
        
        status, company_response = self.make_request('POST', '/companies', data=company_data)
        if status == 200:
            self.company_id = company_response.get('company_id')
            print(f"✅ Company created: {self.company_id}")
        elif status == 400 and "already has a company" in str(company_response):
            print("✅ Company already exists, getting existing one...")
            status, existing = self.make_request('GET', '/companies/my')
            if status == 200:
                self.company_id = existing.get('id')
                print(f"✅ Using existing company: {self.company_id}")
            else:
                print(f"❌ Could not get existing company: {status}")
                return False
        else:
            print(f"❌ Company creation failed: {status} - {company_response}")
            return False
        
        # 4. Manually link carrier profile to company
        print("🔗 Manually linking carrier profile to company...")
        db = self.connect_to_db()
        if db is None:
            print("❌ Database connection failed")
            return False
        
        result = db.carrier_profiles.update_one(
            {"user_id": self.user_id},
            {"$set": {"company_id": self.company_id}}
        )
        
        if result.modified_count > 0:
            print("✅ Carrier profile linked to company")
        else:
            print("⚠️ Profile link update returned 0 modified count")
        
        # 5. Test company info sync
        print("🔄 Testing company info sync...")
        company_data = {
            "company_name": "SYNC TEST Company Updated",
            "phone": "+1-604-555-1234",
            "email": "synctest@updated.ca",
            "website": "https://synctest.ca",
            "address": {
                "street": "999 Sync Test Blvd",
                "city": "Vancouver",
                "province_state": "BC",
                "postal_code": "V6Z 9Z9",
                "country": "CA"
            }
        }
        
        status, update_response = self.make_request('PUT', '/carrier-profiles/company-info', data=company_data)
        if status != 200:
            print(f"❌ Company info update failed: {status}")
            return False
        
        print("✅ Company info updated in carrier profile")
        
        # 6. Check if sync worked in Company collection
        print("🔍 Checking sync in Company collection...")
        company_doc = db.companies.find_one({"id": self.company_id})
        if not company_doc:
            print("❌ Company document not found")
            return False
        
        sync_checks = {
            "name": ("SYNC TEST Company Updated", company_doc.get('name')),
            "phone_number": ("+1-604-555-1234", company_doc.get('phone_number')),
            "company_email": ("synctest@updated.ca", company_doc.get('company_email')),
            "website": ("https://synctest.ca", company_doc.get('website')),
            "address": ("999 Sync Test Blvd", company_doc.get('address')),
            "city": ("Vancouver", company_doc.get('city')),
        }
        
        sync_success = True
        for field, (expected, actual) in sync_checks.items():
            if expected == actual:
                print(f"   ✅ {field}: {actual}")
            else:
                print(f"   ❌ {field}: Expected '{expected}', Got '{actual}'")
                sync_success = False
        
        # 7. Test regulatory numbers sync
        print("🔢 Testing regulatory numbers sync...")
        regulatory_data = {
            "operating_regions": ["CA", "US"],
            "canadian": {
                "nsc_number": "DIRECTSYNC123",
                "cvor_number": "DIRECT-789"
            },
            "us": {
                "usdot_number": "7777777",
                "mc_number": "MC-777777"
            }
        }
        
        status, reg_response = self.make_request('PUT', '/carrier-profiles/regulatory-numbers', data=regulatory_data)
        if status != 200:
            print(f"❌ Regulatory numbers update failed: {status}")
            return False
        
        print("✅ Regulatory numbers updated in carrier profile")
        
        # 8. Check regulatory sync in Company collection
        print("🔍 Checking regulatory sync in Company collection...")
        company_doc = db.companies.find_one({"id": self.company_id})
        
        regulatory_checks = {
            "nsc_number": ("DIRECTSYNC123", company_doc.get('nsc_number')),
            "cvor_number": ("DIRECT-789", company_doc.get('cvor_number')),
            "dot_number": ("7777777", company_doc.get('dot_number')),
            "mc_number": ("MC-777777", company_doc.get('mc_number')),
        }
        
        regulatory_sync_success = True
        for field, (expected, actual) in regulatory_checks.items():
            if expected == actual:
                print(f"   ✅ {field}: {actual}")
            else:
                print(f"   ❌ {field}: Expected '{expected}', Got '{actual}'")
                regulatory_sync_success = False
        
        # 9. Summary
        print("\n" + "=" * 50)
        print("📊 Sync Test Summary:")
        print(f"   Company Info Sync: {'✅ SUCCESS' if sync_success else '❌ FAILED'}")
        print(f"   Regulatory Sync: {'✅ SUCCESS' if regulatory_sync_success else '❌ FAILED'}")
        
        overall_success = sync_success and regulatory_sync_success
        print(f"   Overall: {'✅ ALL SYNC WORKING' if overall_success else '❌ SYNC ISSUES DETECTED'}")
        
        return overall_success

def main():
    tester = DirectSyncTester()
    success = tester.test_sync_verification()
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())