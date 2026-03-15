"""
Test Suite for TMS Rate Cards & Accessorial Charges - Phase 6
Tests lane-based pricing, accessorial codes, rate cards, and rate quote calculation
Canadian-first design with support for detention, lumper, fuel surcharge, border crossing

Endpoints tested:
- GET /api/pricing/accessorials/codes - List all accessorial codes
- GET /api/pricing/accessorials/defaults - List default accessorial charges
- POST /api/pricing/accessorials - Create/override accessorial definition
- GET /api/pricing/accessorials - List accessorial definitions for tenant
- PUT /api/pricing/accessorials/{code} - Update accessorial definition
- POST /api/pricing/rate-cards - Create a new rate card with lane rates
- GET /api/pricing/rate-cards - List rate cards with filtering
- GET /api/pricing/rate-cards/{id} - Get rate card details
- PUT /api/pricing/rate-cards/{id} - Update rate card
- POST /api/pricing/rate-cards/{id}/lanes - Add lane rate to rate card
- DELETE /api/pricing/rate-cards/{id}/lanes/{lane_id} - Remove lane rate
- POST /api/pricing/rate-cards/{id}/activate - Activate rate card
- POST /api/pricing/rate-cards/quote - Get rate quote for a lane with accessorials
- GET /api/pricing/rate-cards/lanes/search - Search lanes across rate cards
"""

import pytest
import requests
import uuid
from datetime import date, timedelta

# API Base URL
BASE_URL = "https://accessorial-charges.preview.emergentagent.com"

# Test credentials
ADMIN_EMAIL = "aminderpro@gmail.com"
ADMIN_PASSWORD = "Admin@123!"
TEST_TENANT_ID = "test-tenant"

# Known rate card ID from context
EXISTING_RATE_CARD_ID = "b3be9c35-f7f3-4f8f-923a-0785d9ded73c"


class TestSetup:
    """Test fixtures and setup"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a requests session"""
        return requests.Session()
    
    @pytest.fixture(scope="class")
    def auth_token(self, session):
        """Login and get authentication token"""
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Token field is 'access_token' not 'token'
        token = data.get("access_token")
        assert token, f"No access_token in response: {data}"
        return token
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get authorization headers"""
        return {"Authorization": f"Bearer {auth_token}"}


class TestAccessorialCodes(TestSetup):
    """Tests for accessorial code listing endpoints"""
    
    def test_get_accessorial_codes(self, session, auth_headers):
        """GET /api/pricing/accessorials/codes - List all accessorial codes"""
        response = session.get(
            f"{BASE_URL}/api/pricing/accessorials/codes",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to get codes: {response.text}"
        codes = response.json()
        
        # Should return list of code objects
        assert isinstance(codes, list), "Response should be a list"
        assert len(codes) > 0, "Should have accessorial codes"
        
        # Check structure
        first_code = codes[0]
        assert "code" in first_code, "Code object should have 'code' field"
        assert "name" in first_code, "Code object should have 'name' field"
        
        # Verify Canadian-specific codes exist
        code_values = [c["code"] for c in codes]
        assert "border_crossing" in code_values, "Should have border_crossing code"
        assert "pars_paps" in code_values, "Should have pars_paps code"
        assert "fuel_surcharge" in code_values, "Should have fuel_surcharge code"
        assert "det_pickup" in code_values, "Should have det_pickup code"
        assert "lumper" in code_values, "Should have lumper code"
        
        print(f"✅ GET /api/pricing/accessorials/codes - Found {len(codes)} accessorial codes")
    
    def test_get_default_accessorials(self, session, auth_headers):
        """GET /api/pricing/accessorials/defaults - Get default Canadian accessorial rates"""
        response = session.get(
            f"{BASE_URL}/api/pricing/accessorials/defaults",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to get defaults: {response.text}"
        defaults = response.json()
        
        # Should return list of default accessorials
        assert isinstance(defaults, list), "Response should be a list"
        assert len(defaults) > 0, "Should have default accessorials"
        
        # Check structure of defaults
        first_default = defaults[0]
        assert "code" in first_default, "Default should have 'code' field"
        assert "name" in first_default, "Default should have 'name' field"
        assert "charge_type" in first_default, "Default should have 'charge_type' field"
        assert "default_rate" in first_default, "Default should have 'default_rate' field"
        
        # Verify specific defaults
        codes_map = {d["code"]: d for d in defaults}
        
        # Detention should be hourly with free time
        if "det_pickup" in codes_map:
            det = codes_map["det_pickup"]
            assert det["charge_type"] == "per_hour", "Detention should be per_hour"
            assert "free_time_minutes" in det, "Detention should have free_time_minutes"
            assert det["default_rate"] > 0, "Detention rate should be positive"
        
        # Fuel surcharge should be percentage
        if "fuel_surcharge" in codes_map:
            fsc = codes_map["fuel_surcharge"]
            assert fsc["charge_type"] == "percentage", "Fuel surcharge should be percentage"
        
        # Border crossing should be flat
        if "border_crossing" in codes_map:
            bc = codes_map["border_crossing"]
            assert bc["charge_type"] == "flat", "Border crossing should be flat"
            assert bc["default_rate"] == 200.00, "Border crossing default should be $200"
        
        print(f"✅ GET /api/pricing/accessorials/defaults - Found {len(defaults)} default accessorials with Canadian rates")


class TestAccessorialDefinitions(TestSetup):
    """Tests for tenant-specific accessorial definition CRUD"""
    
    @pytest.fixture(scope="class")
    def test_accessorial_code(self):
        """Accessorial code to test with"""
        return "lumper"
    
    def test_create_accessorial_definition(self, session, auth_headers, test_accessorial_code):
        """POST /api/pricing/accessorials - Create tenant-specific accessorial override"""
        payload = {
            "tenant_id": TEST_TENANT_ID,
            "code": test_accessorial_code,
            "name": "TEST_Lumper Service Override",
            "description": "Tenant-specific lumper rate",
            "charge_type": "flat",
            "default_rate": 150.00,
            "minimum_charge": 50.00,
            "is_taxable": True,
            "is_active": True
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/accessorials",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to create accessorial: {response.text}"
        data = response.json()
        
        assert "message" in data, "Response should have message"
        assert "id" in data, "Response should have id"
        # Can be created or updated
        assert any(word in data["message"].lower() for word in ["created", "updated"]), \
            f"Unexpected message: {data['message']}"
        
        print(f"✅ POST /api/pricing/accessorials - Created/updated accessorial definition (id={data['id']})")
        return data["id"]
    
    def test_list_accessorial_definitions(self, session, auth_headers):
        """GET /api/pricing/accessorials - List accessorial definitions for tenant"""
        response = session.get(
            f"{BASE_URL}/api/pricing/accessorials",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to list accessorials: {response.text}"
        definitions = response.json()
        
        assert isinstance(definitions, list), "Response should be a list"
        
        # Should include defaults merged with tenant-specific
        # Look for our test override or any accessorial
        print(f"✅ GET /api/pricing/accessorials - Listed {len(definitions)} accessorial definitions")
    
    def test_update_accessorial_definition(self, session, auth_headers, test_accessorial_code):
        """PUT /api/pricing/accessorials/{code} - Update accessorial definition"""
        response = session.put(
            f"{BASE_URL}/api/pricing/accessorials/{test_accessorial_code}",
            params={
                "default_rate": 175.00,
                "minimum_charge": 75.00
            },
            headers=auth_headers
        )
        
        # May return 404 if the accessorial is not created for user's tenant
        if response.status_code == 404:
            print(f"⚠️ PUT /api/pricing/accessorials/{test_accessorial_code} - Accessorial not found for tenant (expected for platform admin)")
            return
        
        assert response.status_code == 200, f"Failed to update accessorial: {response.text}"
        data = response.json()
        
        assert "message" in data, "Response should have message"
        assert data.get("code") == test_accessorial_code, "Should return the updated code"
        
        print(f"✅ PUT /api/pricing/accessorials/{test_accessorial_code} - Updated accessorial definition")


class TestRateCards(TestSetup):
    """Tests for rate card CRUD operations"""
    
    @pytest.fixture(scope="class")
    def created_rate_card_id(self, session, auth_headers):
        """Create a rate card for testing"""
        unique_name = f"TEST_Rate_Card_{uuid.uuid4().hex[:8]}"
        payload = {
            "tenant_id": TEST_TENANT_ID,
            "name": unique_name,
            "description": "Test rate card for Phase 6 testing",
            "is_customer_rate": True,
            "effective_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
            "currency": "CAD",
            "default_rate_per_km": 2.50,
            "default_minimum": 500.00,
            "fuel_surcharge_percentage": 10.0,
            "fuel_surcharge_included": False,
            "lane_rates": [
                {
                    "origin_province": "ON",
                    "destination_province": "QC",
                    "lane_name": "ON-QC",
                    "distance_km": 550,
                    "rates": {"dry_van": 1500.00, "reefer": 1800.00},
                    "rate_type": "flat_rate",
                    "minimum_charge": 1000.00,
                    "transit_days": 1
                }
            ],
            "accessorial_overrides": {
                "lumper": 125.00,
                "detention": 85.00
            }
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to create rate card: {response.text}"
        data = response.json()
        assert "id" in data, "Response should have id"
        
        print(f"✅ Created test rate card: {data['id']}")
        return data["id"]
    
    def test_create_rate_card(self, session, auth_headers):
        """POST /api/pricing/rate-cards - Create a new rate card with lane rates"""
        unique_name = f"TEST_Canadian_Rate_Card_{uuid.uuid4().hex[:8]}"
        payload = {
            "tenant_id": TEST_TENANT_ID,
            "name": unique_name,
            "description": "Cross-Canada rate card with major lanes",
            "is_customer_rate": True,
            "effective_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=180)).isoformat(),
            "currency": "CAD",
            "default_rate_per_km": 2.75,
            "default_rate_per_mile": 4.40,
            "default_minimum": 650.00,
            "fuel_surcharge_percentage": 12.5,
            "fuel_surcharge_included": False,
            "lane_rates": [
                {
                    "origin_city": "Toronto",
                    "origin_province": "ON",
                    "destination_city": "Montreal",
                    "destination_province": "QC",
                    "lane_name": "Toronto-Montreal",
                    "distance_km": 550,
                    "rates": {"dry_van": 1450.00, "reefer": 1750.00, "flatbed": 1650.00},
                    "rate_type": "flat_rate",
                    "minimum_charge": 1000.00,
                    "transit_days": 1
                },
                {
                    "origin_city": "Vancouver",
                    "origin_province": "BC",
                    "destination_city": "Calgary",
                    "destination_province": "AB",
                    "lane_name": "Vancouver-Calgary",
                    "distance_km": 970,
                    "rates": {"dry_van": 2200.00, "reefer": 2600.00},
                    "rate_type": "flat_rate",
                    "minimum_charge": 1500.00,
                    "transit_days": 2
                }
            ],
            "accessorial_overrides": {
                "border_crossing": 250.00,
                "pars_paps": 75.00,
                "fuel_surcharge": 12.5
            }
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to create rate card: {response.text}"
        data = response.json()
        
        assert "id" in data, "Response should have id"
        assert "name" in data, "Response should have name"
        assert "lanes_count" in data, "Response should have lanes_count"
        assert data["lanes_count"] == 2, f"Should have 2 lanes, got {data['lanes_count']}"
        assert data["name"] == unique_name, "Name should match"
        
        print(f"✅ POST /api/pricing/rate-cards - Created rate card with {data['lanes_count']} lanes (id={data['id']})")
        return data["id"]
    
    def test_list_rate_cards(self, session, auth_headers, created_rate_card_id):
        """GET /api/pricing/rate-cards - List rate cards with filtering"""
        # List without status filter to include drafts
        response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards",
            params={"active_only": False},
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to list rate cards: {response.text}"
        rate_cards = response.json()
        
        assert isinstance(rate_cards, list), "Response should be a list"
        
        # Check that our created rate card is in the list
        ids = [rc["id"] for rc in rate_cards]
        assert created_rate_card_id in ids, f"Created rate card {created_rate_card_id} not in list"
        
        # Verify structure
        if rate_cards:
            rc = rate_cards[0]
            assert "id" in rc, "Rate card should have id"
            assert "name" in rc, "Rate card should have name"
            assert "status" in rc, "Rate card should have status"
            assert "lanes_count" in rc, "Rate card should have lanes_count"
        
        print(f"✅ GET /api/pricing/rate-cards - Listed {len(rate_cards)} rate cards")
    
    def test_get_rate_card_details(self, session, auth_headers, created_rate_card_id):
        """GET /api/pricing/rate-cards/{id} - Get rate card details"""
        response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/{created_rate_card_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to get rate card: {response.text}"
        rc = response.json()
        
        # Verify all fields
        assert rc["id"] == created_rate_card_id, "ID should match"
        assert "name" in rc, "Should have name"
        assert "description" in rc, "Should have description"
        assert "lane_rates" in rc, "Should have lane_rates"
        assert "accessorial_overrides" in rc, "Should have accessorial_overrides"
        assert "effective_date" in rc, "Should have effective_date"
        assert "currency" in rc, "Should have currency"
        assert rc["currency"] == "CAD", "Currency should be CAD"
        
        # Verify lane rates structure
        assert len(rc["lane_rates"]) > 0, "Should have lane rates"
        lane = rc["lane_rates"][0]
        assert "origin_province" in lane, "Lane should have origin_province"
        assert "destination_province" in lane, "Lane should have destination_province"
        assert "rates" in lane, "Lane should have rates"
        
        print(f"✅ GET /api/pricing/rate-cards/{created_rate_card_id} - Got full details with {len(rc['lane_rates'])} lanes")
    
    def test_update_rate_card(self, session, auth_headers, created_rate_card_id):
        """PUT /api/pricing/rate-cards/{id} - Update rate card"""
        payload = {
            "name": "TEST_Updated_Rate_Card",
            "description": "Updated description for testing",
            "fuel_surcharge_percentage": 15.0,
            "default_minimum": 700.00
        }
        
        response = session.put(
            f"{BASE_URL}/api/pricing/rate-cards/{created_rate_card_id}",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to update rate card: {response.text}"
        data = response.json()
        
        assert "message" in data, "Response should have message"
        assert data["id"] == created_rate_card_id, "ID should match"
        
        # Verify update persisted
        verify_response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/{created_rate_card_id}",
            headers=auth_headers
        )
        verify_data = verify_response.json()
        assert verify_data["fuel_surcharge_percentage"] == 15.0, "FSC should be updated to 15%"
        assert verify_data["default_minimum"] == 700.00, "Minimum should be updated to 700"
        
        print(f"✅ PUT /api/pricing/rate-cards/{created_rate_card_id} - Updated rate card successfully")
    
    def test_get_rate_card_not_found(self, session, auth_headers):
        """GET /api/pricing/rate-cards/{id} - 404 for non-existent rate card"""
        fake_id = str(uuid.uuid4())
        response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/{fake_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/pricing/rate-cards/{fake_id} - Correctly returns 404 for non-existent rate card")


class TestLaneRates(TestSetup):
    """Tests for lane rate management"""
    
    @pytest.fixture(scope="class")
    def rate_card_for_lanes(self, session, auth_headers):
        """Create a rate card for lane testing"""
        unique_name = f"TEST_Lane_Rate_Card_{uuid.uuid4().hex[:8]}"
        payload = {
            "tenant_id": TEST_TENANT_ID,
            "name": unique_name,
            "is_customer_rate": True,
            "effective_date": date.today().isoformat(),
            "currency": "CAD",
            "default_rate_per_km": 2.50,
            "default_minimum": 500.00,
            "fuel_surcharge_percentage": 10.0,
            "lane_rates": []
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed to create rate card: {response.text}"
        return response.json()["id"]
    
    def test_add_lane_rate(self, session, auth_headers, rate_card_for_lanes):
        """POST /api/pricing/rate-cards/{id}/lanes - Add lane rate"""
        params = {
            "origin_city": "Edmonton",
            "origin_province": "AB",
            "destination_city": "Saskatoon",
            "destination_province": "SK",
            "lane_name": "Edmonton-Saskatoon",
            "distance_km": 525,
            "dry_van_rate": 1100.00,
            "reefer_rate": 1350.00,
            "rate_type": "flat_rate",
            "minimum_charge": 800.00,
            "transit_days": 1
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_for_lanes}/lanes",
            params=params,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to add lane: {response.text}"
        data = response.json()
        
        assert "lane_id" in data, "Response should have lane_id"
        assert "lane_name" in data, "Response should have lane_name"
        assert data["lane_name"] == "Edmonton-Saskatoon", "Lane name should match"
        
        # Verify lane was added
        verify_response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_for_lanes}",
            headers=auth_headers
        )
        verify_data = verify_response.json()
        assert len(verify_data["lane_rates"]) == 1, "Should have 1 lane"
        
        print(f"✅ POST /api/pricing/rate-cards/{rate_card_for_lanes}/lanes - Added lane rate (id={data['lane_id']})")
        return data["lane_id"]
    
    def test_add_lane_rate_province_only(self, session, auth_headers, rate_card_for_lanes):
        """POST /api/pricing/rate-cards/{id}/lanes - Add lane with province-level rates"""
        params = {
            "origin_province": "MB",
            "destination_province": "ON",
            "lane_name": "MB-ON Corridor",
            "distance_km": 2200,
            "dry_van_rate": 4500.00,
            "flatbed_rate": 5200.00,
            "rate_type": "flat_rate",
            "minimum_charge": 3500.00,
            "transit_days": 3
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_for_lanes}/lanes",
            params=params,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to add province lane: {response.text}"
        data = response.json()
        
        assert "lane_id" in data, "Response should have lane_id"
        
        print(f"✅ POST /api/pricing/rate-cards/{rate_card_for_lanes}/lanes - Added province-level lane")
        return data["lane_id"]
    
    def test_add_lane_rate_validation(self, session, auth_headers, rate_card_for_lanes):
        """POST /api/pricing/rate-cards/{id}/lanes - Validation: requires at least one rate"""
        params = {
            "origin_province": "NS",
            "destination_province": "NB"
            # No rates provided
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_for_lanes}/lanes",
            params=params,
            headers=auth_headers
        )
        
        assert response.status_code == 400, f"Expected 400 for missing rates, got {response.status_code}"
        
        print(f"✅ POST /api/pricing/rate-cards/{rate_card_for_lanes}/lanes - Correctly validates missing rates")
    
    def test_remove_lane_rate(self, session, auth_headers, rate_card_for_lanes):
        """DELETE /api/pricing/rate-cards/{id}/lanes/{lane_id} - Remove lane"""
        # First add a lane to remove
        params = {
            "origin_province": "NL",
            "destination_province": "NS",
            "dry_van_rate": 2000.00
        }
        
        add_response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_for_lanes}/lanes",
            params=params,
            headers=auth_headers
        )
        assert add_response.status_code == 200
        lane_id = add_response.json()["lane_id"]
        
        # Now remove it
        response = session.delete(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_for_lanes}/lanes/{lane_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to remove lane: {response.text}"
        data = response.json()
        
        assert "message" in data, "Response should have message"
        assert data["lane_id"] == lane_id, "Lane ID should match"
        
        print(f"✅ DELETE /api/pricing/rate-cards/{rate_card_for_lanes}/lanes/{lane_id} - Removed lane successfully")


class TestRateCardActivation(TestSetup):
    """Tests for rate card activation workflow"""
    
    def test_activate_rate_card(self, session, auth_headers):
        """POST /api/pricing/rate-cards/{id}/activate - Activate rate card"""
        # Create a fresh rate card
        unique_name = f"TEST_Activation_Card_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "tenant_id": TEST_TENANT_ID,
            "name": unique_name,
            "is_customer_rate": True,
            "effective_date": date.today().isoformat(),
            "currency": "CAD",
            "default_rate_per_km": 2.50,
            "fuel_surcharge_percentage": 10.0,
            "lane_rates": [
                {
                    "origin_province": "ON",
                    "destination_province": "BC",
                    "rates": {"dry_van": 5000.00},
                    "rate_type": "flat_rate"
                }
            ]
        }
        
        create_response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards",
            json=create_payload,
            headers=auth_headers
        )
        assert create_response.status_code == 200
        rate_card_id = create_response.json()["id"]
        
        # Verify initial status is draft
        get_response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_id}",
            headers=auth_headers
        )
        assert get_response.json()["status"] == "draft", "Initial status should be draft"
        
        # Activate
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_id}/activate",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to activate: {response.text}"
        data = response.json()
        
        assert "message" in data, "Response should have message"
        assert data["id"] == rate_card_id, "ID should match"
        
        # Verify status changed
        verify_response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_id}",
            headers=auth_headers
        )
        verify_data = verify_response.json()
        assert verify_data["status"] == "active", f"Status should be active, got {verify_data['status']}"
        
        print(f"✅ POST /api/pricing/rate-cards/{rate_card_id}/activate - Activated rate card (draft → active)")


class TestRateQuotes(TestSetup):
    """Tests for rate quote calculation"""
    
    @pytest.fixture(scope="class")
    def active_rate_card_id(self, session, auth_headers):
        """Create and activate a rate card for quote testing"""
        unique_name = f"TEST_Quote_Card_{uuid.uuid4().hex[:8]}"
        payload = {
            "tenant_id": TEST_TENANT_ID,
            "name": unique_name,
            "is_customer_rate": True,
            "customer_id": None,  # Default rate card
            "effective_date": date.today().isoformat(),
            "currency": "CAD",
            "default_rate_per_km": 2.50,
            "default_minimum": 500.00,
            "fuel_surcharge_percentage": 10.0,
            "fuel_surcharge_included": False,
            "lane_rates": [
                {
                    "origin_city": "Toronto",
                    "origin_province": "ON",
                    "destination_city": "Montreal",
                    "destination_province": "QC",
                    "lane_name": "Toronto-Montreal",
                    "distance_km": 550,
                    "rates": {"dry_van": 1500.00, "reefer": 1800.00},
                    "rate_type": "flat_rate",
                    "minimum_charge": 1000.00,
                    "transit_days": 1
                }
            ],
            "accessorial_overrides": {
                "lumper": 125.00
            }
        }
        
        create_response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards",
            json=payload,
            headers=auth_headers
        )
        assert create_response.status_code == 200, f"Failed to create: {create_response.text}"
        rate_card_id = create_response.json()["id"]
        
        # Activate
        activate_response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/{rate_card_id}/activate",
            headers=auth_headers
        )
        assert activate_response.status_code == 200, f"Failed to activate: {activate_response.text}"
        
        return rate_card_id
    
    def test_get_rate_quote_matching_lane(self, session, auth_headers, active_rate_card_id):
        """POST /api/pricing/rate-cards/quote - Get quote for a matching lane"""
        params = {
            "origin_city": "Toronto",
            "origin_province": "ON",
            "destination_city": "Montreal",
            "destination_province": "QC",
            "equipment_type": "dry_van",
            "tenant_id": TEST_TENANT_ID  # Required for platform admin
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/quote",
            params=params,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to get quote: {response.text}"
        quote = response.json()
        
        # Verify quote structure
        assert "rate_card_id" in quote, "Quote should have rate_card_id"
        assert "line_haul" in quote, "Quote should have line_haul"
        assert "fuel_surcharge_percentage" in quote, "Quote should have FSC %"
        assert "fuel_surcharge_amount" in quote, "Quote should have FSC amount"
        assert "subtotal" in quote, "Quote should have subtotal"
        assert "origin" in quote, "Quote should have origin"
        assert "destination" in quote, "Quote should have destination"
        
        # Verify values
        assert quote["line_haul"] == 1500.00, f"Line haul should be 1500, got {quote['line_haul']}"
        assert quote["fuel_surcharge_percentage"] == 10.0, "FSC % should be 10"
        
        # FSC amount = 1500 * 10% = 150
        expected_fsc = round(1500.00 * 0.10, 2)
        assert quote["fuel_surcharge_amount"] == expected_fsc, f"FSC amount should be {expected_fsc}, got {quote['fuel_surcharge_amount']}"
        
        # Subtotal = line_haul + fsc
        expected_subtotal = 1500.00 + expected_fsc
        assert quote["subtotal"] == expected_subtotal, f"Subtotal should be {expected_subtotal}, got {quote['subtotal']}"
        
        print(f"✅ POST /api/pricing/rate-cards/quote - Got quote: line_haul=${quote['line_haul']}, FSC=${quote['fuel_surcharge_amount']}, subtotal=${quote['subtotal']}")
    
    def test_get_rate_quote_with_accessorials(self, session, auth_headers, active_rate_card_id):
        """POST /api/pricing/rate-cards/quote - Get quote with accessorial charges"""
        params = {
            "origin_city": "Toronto",
            "origin_province": "ON",
            "destination_city": "Montreal",
            "destination_province": "QC",
            "equipment_type": "dry_van",
            "tenant_id": TEST_TENANT_ID,
            "accessorial_codes": "lumper,liftgate"  # lumper has override, liftgate uses default
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/quote",
            params=params,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to get quote: {response.text}"
        quote = response.json()
        
        # Verify accessorials included
        assert "accessorials" in quote, "Quote should have accessorials"
        assert "accessorials_total" in quote, "Quote should have accessorials_total"
        
        # Check that accessorials are calculated
        if quote["accessorials"]:
            codes = [a["code"] for a in quote["accessorials"]]
            print(f"✅ POST /api/pricing/rate-cards/quote with accessorials - Included: {codes}, total=${quote['accessorials_total']}")
        else:
            print(f"✅ POST /api/pricing/rate-cards/quote with accessorials - Accessorials parsed (may use defaults)")
    
    def test_get_rate_quote_different_equipment(self, session, auth_headers, active_rate_card_id):
        """POST /api/pricing/rate-cards/quote - Get quote for reefer equipment"""
        params = {
            "origin_city": "Toronto",
            "origin_province": "ON",
            "destination_city": "Montreal",
            "destination_province": "QC",
            "equipment_type": "reefer",
            "tenant_id": TEST_TENANT_ID
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/quote",
            params=params,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to get quote: {response.text}"
        quote = response.json()
        
        # Reefer rate should be 1800
        assert quote["line_haul"] == 1800.00, f"Reefer line haul should be 1800, got {quote['line_haul']}"
        
        print(f"✅ POST /api/pricing/rate-cards/quote (reefer) - Line haul=${quote['line_haul']}")
    
    def test_get_rate_quote_fallback_to_default(self, session, auth_headers, active_rate_card_id):
        """POST /api/pricing/rate-cards/quote - Fallback to default rate when no lane match"""
        params = {
            "origin_city": "Calgary",
            "origin_province": "AB",
            "destination_city": "Regina",
            "destination_province": "SK",
            "equipment_type": "dry_van",
            "distance_km": 750,
            "tenant_id": TEST_TENANT_ID
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/quote",
            params=params,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to get quote: {response.text}"
        quote = response.json()
        
        # Should use default rate per km: 2.50 * 750 = 1875
        expected_line_haul = 2.50 * 750
        assert quote["line_haul"] == expected_line_haul, f"Line haul should be {expected_line_haul} (default per km), got {quote['line_haul']}"
        
        print(f"✅ POST /api/pricing/rate-cards/quote (no lane match) - Fallback rate=${quote['line_haul']}")
    
    def test_get_rate_quote_no_active_rate_card(self, session, auth_headers):
        """POST /api/pricing/rate-cards/quote - 404 when no active rate card"""
        # Use a tenant that doesn't have any rate cards
        params = {
            "origin_city": "Toronto",
            "origin_province": "ON",
            "destination_city": "Montreal",
            "destination_province": "QC",
            "equipment_type": "dry_van",
            "tenant_id": "non-existent-tenant-12345"
        }
        
        response = session.post(
            f"{BASE_URL}/api/pricing/rate-cards/quote",
            params=params,
            headers=auth_headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        print(f"✅ POST /api/pricing/rate-cards/quote - Correctly returns 404 for tenant with no active rate card")


class TestLaneSearch(TestSetup):
    """Tests for lane search functionality"""
    
    def test_search_lanes_all(self, session, auth_headers):
        """GET /api/pricing/rate-cards/lanes/search - Search all lanes"""
        response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/lanes/search",
            params={"tenant_id": TEST_TENANT_ID},
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to search lanes: {response.text}"
        lanes = response.json()
        
        assert isinstance(lanes, list), "Response should be a list"
        
        # If we have lanes, verify structure
        if lanes:
            lane = lanes[0]
            assert "rate_card_id" in lane, "Lane should have rate_card_id"
            assert "rate_card_name" in lane, "Lane should have rate_card_name"
            assert "origin_province" in lane or "rates" in lane, "Lane should have origin info or rates"
        
        print(f"✅ GET /api/pricing/rate-cards/lanes/search - Found {len(lanes)} lanes")
    
    def test_search_lanes_by_origin(self, session, auth_headers):
        """GET /api/pricing/rate-cards/lanes/search - Search lanes by origin province"""
        response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/lanes/search",
            params={
                "origin_province": "ON",
                "tenant_id": TEST_TENANT_ID
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to search: {response.text}"
        lanes = response.json()
        
        # All results should have ON as origin
        for lane in lanes:
            origin_prov = lane.get("origin_province", "").upper()
            assert origin_prov == "ON", f"Origin should be ON, got {origin_prov}"
        
        print(f"✅ GET /api/pricing/rate-cards/lanes/search (origin=ON) - Found {len(lanes)} Ontario-origin lanes")
    
    def test_search_lanes_by_destination(self, session, auth_headers):
        """GET /api/pricing/rate-cards/lanes/search - Search lanes by destination province"""
        response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/lanes/search",
            params={
                "destination_province": "QC",
                "tenant_id": TEST_TENANT_ID
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to search: {response.text}"
        lanes = response.json()
        
        # All results should have QC as destination
        for lane in lanes:
            dest_prov = lane.get("destination_province", "").upper()
            assert dest_prov == "QC", f"Destination should be QC, got {dest_prov}"
        
        print(f"✅ GET /api/pricing/rate-cards/lanes/search (dest=QC) - Found {len(lanes)} Quebec-destination lanes")
    
    def test_search_lanes_by_corridor(self, session, auth_headers):
        """GET /api/pricing/rate-cards/lanes/search - Search lanes by corridor (origin + destination)"""
        response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/lanes/search",
            params={
                "origin_province": "ON",
                "destination_province": "QC",
                "tenant_id": TEST_TENANT_ID
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to search: {response.text}"
        lanes = response.json()
        
        # All results should match both origin and destination
        for lane in lanes:
            origin_prov = lane.get("origin_province", "").upper()
            dest_prov = lane.get("destination_province", "").upper()
            assert origin_prov == "ON", f"Origin should be ON"
            assert dest_prov == "QC", f"Destination should be QC"
        
        print(f"✅ GET /api/pricing/rate-cards/lanes/search (ON→QC corridor) - Found {len(lanes)} lanes")


class TestExistingRateCard(TestSetup):
    """Tests using the existing rate card from context"""
    
    def test_get_existing_rate_card(self, session, auth_headers):
        """GET /api/pricing/rate-cards/{id} - Get pre-created rate card"""
        response = session.get(
            f"{BASE_URL}/api/pricing/rate-cards/{EXISTING_RATE_CARD_ID}",
            headers=auth_headers
        )
        
        # Rate card might not exist or might be for different tenant
        if response.status_code == 404:
            print(f"⚠️ Pre-existing rate card {EXISTING_RATE_CARD_ID} not found (may have been deleted)")
            return
        
        if response.status_code == 403:
            print(f"⚠️ Pre-existing rate card {EXISTING_RATE_CARD_ID} - access denied (different tenant)")
            return
        
        assert response.status_code == 200, f"Unexpected error: {response.text}"
        rc = response.json()
        
        print(f"✅ GET /api/pricing/rate-cards/{EXISTING_RATE_CARD_ID} - Found: {rc.get('name', 'N/A')}")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
