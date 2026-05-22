import subprocess
import time
import urllib.request
import json
import asyncio
import websockets
import sys

# Reconfigure stdout/stderr to use UTF-8 to prevent encoding crashes on Windows cmd/powershell
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

async def listen_events(ws, log_store):
    try:
        async for message in ws:
            data = json.loads(message)
            msg_id = data.get("id")
            method = data.get("method")
            params = data.get("params", {})
            
            # Save RPC responses
            if msg_id is not None:
                log_store["responses"][msg_id] = data
            
            if method == "Runtime.consoleAPICalled":
                msg_type = params.get("type")
                args = params.get("args", [])
                text = " ".join([str(arg.get("value", "")) for arg in args])
                log_store["console"].append({"type": msg_type, "text": text})
                print(f"[Console {msg_type.upper()}] {text}")
                
            elif method == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails", {})
                exc_text = details.get("exception", {}).get("description", "") or details.get("text", "")
                log_store["exceptions"].append(exc_text)
                print(f"[Exception] {exc_text}")
                
            elif method == "Log.entryAdded":
                entry = params.get("entry", {})
                level = entry.get("level")
                text = entry.get("text")
                log_store["logs"].append({"level": level, "text": text})
                print(f"[Log {level.upper()}] {text}")
                
            elif method == "Network.responseReceived":
                response = params.get("response", {})
                status = response.get("status")
                url = response.get("url")
                if status >= 400:
                    log_store["network_errors"].append({"url": url, "status": status})
                    print(f"[Network Error] {url} returned status {status}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Event listener error: {e}")

async def run_verification():
    # 1. Start Chrome
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    print("Launching Chrome...")
    chrome_proc = subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        "--headless",
        "--disable-gpu",
        "--no-sandbox"
    ])
    
    # Wait for Chrome to boot
    time.sleep(2)
    
    log_store = {
        "console": [],
        "exceptions": [],
        "logs": [],
        "network_errors": [],
        "responses": {}
    }
    
    try:
        # 2. Get WebSocket URL
        req = urllib.request.Request("http://127.0.0.1:9222/json")
        with urllib.request.urlopen(req) as response:
            targets = json.loads(response.read().decode('utf-8'))
            
        page_target = None
        for t in targets:
            if t.get("type") == "page":
                page_target = t
                break
                
        if not page_target:
            print("No page target found.")
            return
            
        ws_url = page_target["webSocketDebuggerUrl"]
        print(f"Connecting to page WS: {ws_url}")
        
        async with websockets.connect(ws_url) as ws:
            # Start event listener
            listener_task = asyncio.create_task(listen_events(ws, log_store))
            
            # Enable domains
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "Log.enable"}))
            await ws.send(json.dumps({"id": 4, "method": "Network.enable"}))
            
            # 3. Navigate to login / home
            print("Navigating to http://localhost:5029...")
            await ws.send(json.dumps({
                "id": 5,
                "method": "Page.navigate",
                "params": {"url": "http://localhost:5029"}
            }))
            
            # Wait for startup load & Blazor boot
            print("Waiting 6 seconds for startup and Blazor initialization...")
            await asyncio.sleep(6)
            
            # Query DOM for login button or page structure
            print("\nChecking login page DOM...")
            get_login_page_expr = """
            (() => {
                const title = document.querySelector('.login-card h2');
                const quickButtons = Array.from(document.querySelectorAll('.quick-user-btn')).map(b => b.textContent.trim());
                return {
                    title: title ? title.textContent : null,
                    quickButtons: quickButtons
                };
            })()
            """
            
            query_id = 100
            await ws.send(json.dumps({
                "id": query_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": get_login_page_expr,
                    "returnByValue": True
                }
            }))
            
            while query_id not in log_store["responses"]:
                await asyncio.sleep(0.1)
            
            login_info = log_store["responses"][query_id].get("result", {}).get("result", {}).get("value", {})
            print(f"Login Page Info: {login_info}")
            
            # 4. Perform Login by clicking the first quick login button ("Олексій")
            print("\nSimulating click on first quick user login button...")
            click_login_expr = """
            (async () => {
                const buttons = Array.from(document.querySelectorAll('.quick-user-btn'));
                if (buttons.length === 0) throw new Error('No quick login buttons found');
                buttons[0].click(); // Click "Олексій"
                return "Clicked first user";
            })()
            """
            
            eval_id = 200
            await ws.send(json.dumps({
                "id": eval_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": click_login_expr,
                    "awaitPromise": True,
                    "returnByValue": True
                }
            }))
            
            while eval_id not in log_store["responses"]:
                await asyncio.sleep(0.1)
            
            click_res = log_store["responses"][eval_id]
            print(f"Click response: {json.dumps(click_res.get('result', {}), indent=2)}")
            
            # Wait for Blazor navigation and load
            print("Waiting 5 seconds for redirection and main layout render...")
            await asyncio.sleep(5)
            
            # Query DOM for sidebar profile info
            print("\nQuerying sidebar user profile info...")
            get_profile_expr = """
            (() => {
                const userNameEl = document.querySelector('.user-profile-btn .user-name');
                const sidebarAddBtn = document.querySelector('.sidebar-add-btn');
                return {
                    userName: userNameEl ? userNameEl.textContent.trim() : null,
                    hasAddBtn: !!sidebarAddBtn
                };
            })()
            """
            
            query_id_2 = 300
            await ws.send(json.dumps({
                "id": query_id_2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": get_profile_expr,
                    "returnByValue": True
                }
            }))
            
            while query_id_2 not in log_store["responses"]:
                await asyncio.sleep(0.1)
                
            profile_info = log_store["responses"][query_id_2].get("result", {}).get("result", {}).get("value", {})
            print(f"Profile info in sidebar: {profile_info}")
            
            # 5. Open Personal Cabinet
            print("\nOpening Personal Cabinet...")
            open_cabinet_expr = """
            (() => {
                const btn = document.querySelector('.user-profile-btn');
                if (!btn) throw new Error('Profile button not found');
                btn.click();
                return "Clicked profile";
            })()
            """
            
            eval_id_2 = 400
            await ws.send(json.dumps({
                "id": eval_id_2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": open_cabinet_expr,
                    "returnByValue": True
                }
            }))
            
            while eval_id_2 not in log_store["responses"]:
                await asyncio.sleep(0.1)
                
            # Wait for Cabinet modal to render
            print("Waiting 2 seconds for Cabinet to render...")
            await asyncio.sleep(2)
            
            # Query Cabinet info
            print("\nQuerying Cabinet Modal content...")
            get_cabinet_expr = """
            (() => {
                const modal = document.querySelector('.cabinet-modal');
                if (!modal) return null;
                const title = modal.querySelector('.modal-title') ? modal.querySelector('.modal-title').textContent.trim() : '';
                const role = modal.querySelector('.user-role-badge') ? modal.querySelector('.user-role-badge').textContent.trim() : '';
                const stats = Array.from(modal.querySelectorAll('.stat-card')).map(card => {
                    const label = card.querySelector('.stat-label') ? card.querySelector('.stat-label').textContent.trim() : '';
                    const val = card.querySelector('.stat-value') ? card.querySelector('.stat-value').textContent.trim() : '';
                    return { label, val };
                });
                return {
                    title,
                    role,
                    stats
                };
            })()
            """
            
            query_id_3 = 500
            await ws.send(json.dumps({
                "id": query_id_3,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": get_cabinet_expr,
                    "returnByValue": True
                }
            }))
            
            while query_id_3 not in log_store["responses"]:
                await asyncio.sleep(0.1)
                
            cabinet_info = log_store["responses"][query_id_3].get("result", {}).get("result", {}).get("value", {})
            print(f"Cabinet Modal Info: {cabinet_info}")
            
            # Close the Personal Cabinet
            print("\nClosing Personal Cabinet...")
            close_cabinet_expr = """
            (() => {
                const closeBtn = document.querySelector('.cabinet-close');
                if (!closeBtn) throw new Error('Cabinet close button not found');
                closeBtn.click();
                return "Closed cabinet";
            })()
            """
            
            eval_id_3 = 600
            await ws.send(json.dumps({
                "id": eval_id_3,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": close_cabinet_expr,
                    "returnByValue": True
                }
            }))
            
            while eval_id_3 not in log_store["responses"]:
                await asyncio.sleep(0.1)
                
            await asyncio.sleep(1)
            print("\nVerification process complete!")
            
            # Cancel the listener
            listener_task.cancel()
            await asyncio.gather(listener_task, return_exceptions=True)
            
    finally:
        print("Terminating Chrome...")
        chrome_proc.terminate()
        chrome_proc.wait()
        print("Chrome terminated.")
        
    report = {
        "login_info": login_info,
        "profile_info": profile_info,
        "cabinet_info": cabinet_info,
        "log_store": {
            "console": log_store["console"],
            "exceptions": log_store["exceptions"],
            "logs": log_store["logs"],
            "network_errors": log_store["network_errors"]
        }
    }
    with open("c:\\Taras\\Vibe Test\\phase2_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("Report written to phase2_report.json")

if __name__ == "__main__":
    asyncio.run(run_verification())
