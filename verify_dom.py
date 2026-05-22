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
            
            # 3. Navigate
            print("Navigating to http://localhost:5029...")
            await ws.send(json.dumps({
                "id": 5,
                "method": "Page.navigate",
                "params": {"url": "http://localhost:5029"}
            }))
            
            # Wait for startup load & Blazor boot
            print("Waiting 6 seconds for startup and Blazor initialization...")
            await asyncio.sleep(6)
            
            # Query DOM for existing .node-name elements
            print("\nQuerying existing spaces in sidebar DOM...")
            get_dom_expr = """
            (() => {
                const els = Array.from(document.querySelectorAll('.node-name'));
                return els.map(e => e.textContent ? e.textContent.trim() : '');
            })()
            """
            
            query_id = 100
            await ws.send(json.dumps({
                "id": query_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": get_dom_expr,
                    "returnByValue": True
                }
            }))
            
            # Wait for response in log_store
            while query_id not in log_store["responses"]:
                await asyncio.sleep(0.1)
            
            initial_spaces = log_store["responses"][query_id].get("result", {}).get("result", {}).get("value", [])
            print(f"Initial spaces in DOM: {initial_spaces}")
            
            # 4. Simulate creating a new Space
            print("\nSimulating creation of a new Space (Space_DOM_Check)...")
            js_create_expr = """
            (async () => {
                const addBtn = document.querySelector('.sidebar-add-btn');
                if (!addBtn) throw new Error('Add button not found');
                addBtn.click();
                
                await new Promise(r => setTimeout(r, 600));
                
                const input = document.querySelector('.modal-window .form-input');
                if (!input) throw new Error('Input field not found');
                
                const spaceName = 'Space_DOM_Check';
                input.value = spaceName;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                
                await new Promise(r => setTimeout(r, 300));
                
                const buttons = Array.from(document.querySelectorAll('.modal-footer .btn-primary'));
                const createBtn = buttons.find(b => b.textContent.includes('Створити'));
                if (!createBtn) throw new Error('Create button not found');
                createBtn.click();
                
                return spaceName;
            })()
            """
            
            eval_id = 200
            await ws.send(json.dumps({
                "id": eval_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": js_create_expr,
                    "awaitPromise": True,
                    "returnByValue": True
                }
            }))
            
            while eval_id not in log_store["responses"]:
                await asyncio.sleep(0.1)
            
            create_res = log_store["responses"][eval_id]
            print(f"Create space call finished. Result/Error: {json.dumps(create_res.get('result', {}), indent=2)}")
            
            # Wait a few seconds for render
            print("Waiting 4 seconds for Blazor to complete render phase...")
            await asyncio.sleep(4)
            
            # Query DOM again for .node-name elements
            query_id_2 = 300
            await ws.send(json.dumps({
                "id": query_id_2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": get_dom_expr,
                    "returnByValue": True
                }
            }))
            
            while query_id_2 not in log_store["responses"]:
                await asyncio.sleep(0.1)
                
            final_spaces = log_store["responses"][query_id_2].get("result", {}).get("result", {}).get("value", [])
            print(f"Final spaces in DOM: {final_spaces}")
            
            # Cancel the listener
            listener_task.cancel()
            await asyncio.gather(listener_task, return_exceptions=True)
            
    finally:
        print("Terminating Chrome...")
        chrome_proc.terminate()
        chrome_proc.wait()
        print("Chrome terminated.")
        
    # Write report file
    report = {
        "initial_spaces": initial_spaces,
        "final_spaces": final_spaces,
        "log_store": {
            "console": log_store["console"],
            "exceptions": log_store["exceptions"],
            "logs": log_store["logs"],
            "network_errors": log_store["network_errors"]
        }
    }
    with open("c:\\Taras\\Vibe Test\\dom_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print("Report written to dom_report.json")

if __name__ == "__main__":
    asyncio.run(run_verification())
