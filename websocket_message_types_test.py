#!/usr/bin/env python3
"""
Test the specific WebSocket message types: realtime_update and overview_update
"""

import asyncio
import websockets
import json
import requests
import time
import uuid

async def test_websocket_message_types():
    """Test specific WebSocket message types"""
    print("🧪 Testing WebSocket Message Types: realtime_update and overview_update")
    print("=" * 70)
    
    ws_url = "ws://localhost:8001/api/ws/analytics"
    base_url = "http://localhost:8001"
    messages_received = []
    
    try:
        # Connect to WebSocket
        async with websockets.connect(ws_url) as websocket:
            print("✅ WebSocket connected")
            
            # Listen for messages in background
            async def listen():
                try:
                    while True:
                        message = await websocket.recv()
                        try:
                            data = json.loads(message)
                            messages_received.append(data)
                            print(f"📥 Received {data['type']}: {json.dumps(data['payload'], indent=2)}")
                        except:
                            messages_received.append(message)
                            print(f"📥 Raw: {message}")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"⚠️ Listen error: {e}")
            
            # Start listening
            listen_task = asyncio.create_task(listen())
            
            # Wait for connection stability
            await asyncio.sleep(1)
            
            # Generate multiple analytics events to trigger different message types
            print("\n🎯 Generating analytics events to test broadcasts...")
            
            loop = asyncio.get_event_loop()
            
            # Generate 3 different visitor sessions to test realtime updates
            for i in range(3):
                visitor_id = str(uuid.uuid4())
                session_id = str(uuid.uuid4())
                
                # Start session
                session_data = {
                    "visitor_id": visitor_id,
                    "landing_page": f"/page{i}",
                    "referrer": "https://google.com",
                    "user_agent": "Test Browser"
                }
                
                start_url = f"{base_url}/api/customer-analytics/track/session/start"
                await loop.run_in_executor(None, lambda: requests.post(start_url, json=session_data))
                
                # Track pageview
                pageview_data = {
                    "page_url": f"/page{i}",
                    "page_title": f"Test Page {i}",
                    "session_id": session_id,
                    "visitor_id": visitor_id
                }
                pageview_url = f"{base_url}/api/customer-analytics/track/pageview"
                await loop.run_in_executor(None, lambda: requests.post(pageview_url, json=pageview_data))
                
                # Track conversion (should trigger overview_update)
                conversion_data = {
                    "event_name": f"test_conversion_{i}",
                    "event_category": "test",
                    "event_value": 25.0 * (i + 1),
                    "page_url": f"/page{i}",
                    "session_id": session_id,
                    "visitor_id": visitor_id
                }
                conversion_url = f"{base_url}/api/customer-analytics/track/conversion"
                await loop.run_in_executor(None, lambda: requests.post(conversion_url, json=conversion_data))
                
                print(f"   ✅ Generated events for visitor {i+1}")
                await asyncio.sleep(0.5)  # Small delay between events
            
            # Wait for all broadcasts
            await asyncio.sleep(3)
            
            # Cancel listening
            listen_task.cancel()
            
            # Analyze received messages
            print(f"\n📊 Analysis of {len(messages_received)} WebSocket messages:")
            
            realtime_updates = [msg for msg in messages_received if msg.get('type') == 'realtime_update']
            overview_updates = [msg for msg in messages_received if msg.get('type') == 'overview_update']
            new_visitors = [msg for msg in messages_received if msg.get('type') == 'new_visitor']
            new_pageviews = [msg for msg in messages_received if msg.get('type') == 'new_pageview']
            new_conversions = [msg for msg in messages_received if msg.get('type') == 'new_conversion']
            
            print(f"   📈 realtime_update messages: {len(realtime_updates)}")
            print(f"   📊 overview_update messages: {len(overview_updates)}")
            print(f"   👤 new_visitor messages: {len(new_visitors)}")
            print(f"   📄 new_pageview messages: {len(new_pageviews)}")
            print(f"   🎯 new_conversion messages: {len(new_conversions)}")
            
            # Check if we got the required message types
            success = True
            
            if realtime_updates:
                print("\n✅ realtime_update messages received:")
                for msg in realtime_updates[:2]:  # Show first 2
                    payload = msg.get('payload', {})
                    print(f"   📈 Active visitors: {payload.get('active_visitors', 'N/A')}")
                    print(f"   📈 Active sessions: {payload.get('active_sessions', 'N/A')}")
            else:
                print("\n⚠️ No realtime_update messages received")
                success = False
            
            if overview_updates:
                print("\n✅ overview_update messages received:")
                for msg in overview_updates[:2]:  # Show first 2
                    payload = msg.get('payload', {})
                    print(f"   📊 Total visitors: {payload.get('total_visitors', 'N/A')}")
                    print(f"   📊 Conversions: {payload.get('conversions', 'N/A')}")
            else:
                print("\n⚠️ No overview_update messages received")
                success = False
            
            return success, len(messages_received)
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False, 0

async def main():
    """Main test runner"""
    success, msg_count = await test_websocket_message_types()
    
    print(f"\n📋 Summary:")
    print(f"   Test Result: {'✅ PASSED' if success else '❌ FAILED'}")
    print(f"   Messages Received: {msg_count}")
    
    if success:
        print("   🎉 Both realtime_update and overview_update message types are working!")
    else:
        print("   ⚠️ Some expected message types were not received")
    
    return 0 if success else 1

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(result)