#!/usr/bin/env python3
"""
Simple WebSocket Test for Analytics
"""
import websocket
import json
import time
import threading
import requests

def on_message(ws, message):
    print(f"📨 Received WebSocket message: {message}")

def on_error(ws, error):
    print(f"❌ WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("🔌 WebSocket connection closed")

def on_open(ws):
    print("✅ WebSocket connection opened")
    
    # Send a ping
    ws.send("ping")
    
    # Wait a moment then trigger some events
    def send_test_events():
        time.sleep(1)
        
        # Send a session start event
        print("📤 Sending session start...")
        session_data = {
            "visitor_id": "test-visitor-123",
            "landing_page": "https://test.com/",
            "referrer": "https://google.com"
        }
        try:
            response = requests.post(
                "http://localhost:8001/api/customer-analytics/track/session/start",
                json=session_data,
                timeout=5
            )
            print(f"   Session response: {response.status_code}")
        except Exception as e:
            print(f"   Session error: {e}")
        
        time.sleep(1)
        
        # Send a pageview event
        print("📤 Sending pageview...")
        pageview_data = {
            "page_url": "https://test.com/products",
            "page_title": "Products",
            "visitor_id": "test-visitor-123"
        }
        try:
            response = requests.post(
                "http://localhost:8001/api/customer-analytics/track/pageview",
                json=pageview_data,
                timeout=5
            )
            print(f"   Pageview response: {response.status_code}")
        except Exception as e:
            print(f"   Pageview error: {e}")
            
        time.sleep(1)
        
        # Send a conversion event  
        print("📤 Sending conversion...")
        conversion_data = {
            "event_name": "test_conversion",
            "event_category": "demo_request",
            "visitor_id": "test-visitor-123"
        }
        try:
            response = requests.post(
                "http://localhost:8001/api/customer-analytics/track/conversion",
                json=conversion_data,
                timeout=5
            )
            print(f"   Conversion response: {response.status_code}")
        except Exception as e:
            print(f"   Conversion error: {e}")
        
        # Close WebSocket after events
        time.sleep(2)
        ws.close()
    
    # Start event sending in background
    thread = threading.Thread(target=send_test_events)
    thread.start()

def test_websocket():
    print("🧪 Testing WebSocket Analytics Broadcasting")
    print("=" * 50)
    
    ws_url = "ws://localhost:8001/api/ws/analytics"
    print(f"🔌 Connecting to: {ws_url}")
    
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    # Run WebSocket client
    ws.run_forever()
    
    print("🏁 WebSocket test completed")

if __name__ == "__main__":
    test_websocket()