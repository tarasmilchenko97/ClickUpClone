import subprocess
import time
import urllib.request
import json
import asyncio
import websockets
import sys
import os
import base64

# Reconfigure stdout/stderr to use UTF-8 to prevent encoding crashes on Windows cmd/powershell
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Global state for managing responses and events
pending_responses = {}
log_store = {
    "console": [],
    "exceptions": [],
    "logs": [],
    "network_errors": [],
}
id_counter = [1000]

async def listen_events(ws):
    try:
        async for message in ws:
            data = json.loads(message)
            msg_id = data.get("id")
            method = data.get("method")
            params = data.get("params", {})
            
            # If this is a response to a pending request, resolve the future
            if msg_id is not None and msg_id in pending_responses:
                fut = pending_responses.pop(msg_id)
                if not fut.done():
                    fut.set_result(data)
            
            # Track console logs
            if method == "Runtime.consoleAPICalled":
                msg_type = params.get("type")
                args = params.get("args", [])
                text = " ".join([str(arg.get("value", arg.get("description", ""))) for arg in args])
                log_store["console"].append({"type": msg_type, "text": text})
                print(f"[Console {msg_type.upper()}] {text}")
                
            # Track runtime exceptions
            elif method == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails", {})
                exc_text = details.get("exception", {}).get("description", "") or details.get("text", "")
                log_store["exceptions"].append(exc_text)
                print(f"[Exception] {exc_text}")
                
            # Track system log entries
            elif method == "Log.entryAdded":
                entry = params.get("entry", {})
                level = entry.get("level")
                text = entry.get("text")
                log_store["logs"].append({"level": level, "text": text})
                print(f"[Log {level.upper()}] {text}")
                
            # Track network errors
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

async def call_cdp(ws, method, params=None):
    cmd_id = id_counter[0]
    id_counter[0] += 1
    msg = {"id": cmd_id, "method": method}
    if params is not None:
        msg["params"] = params
    
    # Create future to wait for response
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    pending_responses[cmd_id] = fut
    
    await ws.send(json.dumps(msg))
    response = await fut
    
    if "error" in response:
        raise Exception(f"CDP Error in {method}: {response['error']}")
    return response.get("result", {})

async def eval_js(ws, expr):
    res = await call_cdp(ws, "Runtime.evaluate", {
        "expression": expr,
        "awaitPromise": True,
        "returnByValue": True
    })
    result_val = res.get("result", {})
    if "subtype" in result_val and result_val["subtype"] == "error":
        raise Exception(f"JS Exception: {result_val.get('description', 'Unknown error')}")
    return result_val.get("value")

async def wait_for_element(ws, selector, timeout=15):
    print(f"Waiting for element: '{selector}'...")
    start = time.time()
    # Check if element exists in the DOM
    check_expr = f"!!document.querySelector('{selector}')"
    while time.time() - start < timeout:
        try:
            found = await eval_js(ws, check_expr)
            if found:
                print(f"Element '{selector}' found.")
                return True
        except Exception as e:
            # Silently ignore errors during load/reload
            pass
        await asyncio.sleep(0.2)
    print(f"Element '{selector}' NOT found within {timeout}s.")
    return False

async def capture_and_save_screenshot(ws, filepath):
    print(f"Capturing screenshot: {filepath}")
    res = await call_cdp(ws, "Page.captureScreenshot", {"format": "png"})
    img_data = base64.b64decode(res["data"])
    with open(filepath, "wb") as f:
        f.write(img_data)
    print(f"Screenshot saved to {filepath}")

async def run_scenario():
    artifact_dir = r"C:\Users\milch\.gemini\antigravity\brain\0018680f-65fb-48fd-ad11-40a83aefffaa"
    os.makedirs(artifact_dir, exist_ok=True)
    
    # Create a dummy image for testing file upload
    dummy_img_path = os.path.abspath("dummy_upload.png")
    with open(dummy_img_path, "wb") as f:
        # 1x1 white PNG
        f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="))
    print(f"Dummy upload file created at {dummy_img_path}")
    
    # Launch Chrome
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    print("Launching Chrome...")
    chrome_proc = subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        "--headless",
        "--disable-gpu",
        "--no-sandbox"
    ])
    
    # Wait for Chrome to initialize
    await asyncio.sleep(2)
    
    try:
        # Get WebSocket URL
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
            listener_task = asyncio.create_task(listen_events(ws))
            
            # Enable CDP domains
            await call_cdp(ws, "Page.enable")
            await call_cdp(ws, "Runtime.enable")
            await call_cdp(ws, "Log.enable")
            await call_cdp(ws, "Network.enable")
            await call_cdp(ws, "DOM.enable")
            
            # Set Desktop Viewport (1440x900)
            await call_cdp(ws, "Emulation.setDeviceMetricsOverride", {
                "width": 1440,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False
            })
            
            # Navigate to app
            print("Navigating to http://localhost:5029...")
            await call_cdp(ws, "Page.navigate", {"url": "http://localhost:5029"})
            
            # Wait for login form
            login_form_ready = await wait_for_element(ws, "#email", timeout=15)
            if not login_form_ready:
                # If #email is not ready, check if quick login buttons are there
                quick_btn_ready = await wait_for_element(ws, ".quick-user-btn", timeout=5)
                if not quick_btn_ready:
                    raise Exception("Login form elements did not render in time")
            
            # Take login page screenshot
            await capture_and_save_screenshot(ws, os.path.join(artifact_dir, "0_login_page.png"))
            
            # Fill in Login credentials
            print("Filling in login credentials...")
            login_js = """
            (() => {
                const emailInput = document.querySelector('#email');
                const passwordInput = document.querySelector('#password');
                if (!emailInput || !passwordInput) return false;
                
                emailInput.value = 'oleksiy@clickup.com';
                emailInput.dispatchEvent(new Event('input', { bubbles: true }));
                emailInput.dispatchEvent(new Event('change', { bubbles: true }));
                
                passwordInput.value = 'developer';
                passwordInput.dispatchEvent(new Event('input', { bubbles: true }));
                passwordInput.dispatchEvent(new Event('change', { bubbles: true }));
                
                return true;
            })()
            """
            success = await eval_js(ws, login_js)
            if not success:
                print("Testing quick login button fallback...")
                quick_login_js = """
                (() => {
                    const buttons = Array.from(document.querySelectorAll('.quick-user-btn'));
                    const devBtn = buttons.find(b => b.textContent.includes('Олексій'));
                    if (devBtn) {
                        devBtn.click();
                        return true;
                    }
                    return false;
                })()
                """
                success = await eval_js(ws, quick_login_js)
                if not success:
                    raise Exception("Could not fill form or find quick login button")
            else:
                # If form fill was successful, click submit
                print("Form filled successfully. Clicking submit button...")
                await eval_js(ws, "document.querySelector('.btn-submit').click()")
                
            # Wait for sidebar to load (indicates successful login)
            print("Waiting for main screen / sidebar to render after login...")
            sidebar_ready = await wait_for_element(ws, ".sidebar", timeout=15)
            if not sidebar_ready:
                raise Exception("Sidebar did not render after login (possible login failure)")
                
            # Take screenshot right after login
            await capture_and_save_screenshot(ws, os.path.join(artifact_dir, "1_login_success.png"))
            
            # Select 'Розробка сайту' list in the sidebar
            print("Looking for 'Розробка сайту' in sidebar...")
            node_ready = await wait_for_element(ws, ".node-row", timeout=10)
            if not node_ready:
                raise Exception("Sidebar node rows did not render")
                
            click_node_js = """
            (() => {
                const nodes = Array.from(document.querySelectorAll('.node-row'));
                const targetNode = nodes.find(n => n.querySelector('.node-name') && n.querySelector('.node-name').textContent.trim() === 'Розробка сайту');
                if (targetNode) {
                    targetNode.click();
                    return true;
                }
                return false;
            })()
            """
            clicked = await eval_js(ws, click_node_js)
            if not clicked:
                raise Exception("Failed to find or click 'Розробка сайту' node in sidebar")
                
            # Wait for tasks view area to load (welcome screen goes away, task views render)
            print("Waiting for tasks area to load...")
            # We can wait for the view tabs or board columns to appear
            tabs_ready = await wait_for_element(ws, ".view-tabs", timeout=10)
            if not tabs_ready:
                raise Exception("View tabs in main header did not render")
                
            # Wait a moment for tasks to render in default Kanban view
            await asyncio.sleep(2)
            
            # Capture Board view
            await capture_and_save_screenshot(ws, os.path.join(artifact_dir, "2_board_view.png"))
            
            # Switch to List View
            print("Switching to List view...")
            switch_to_list_js = """
            (() => {
                const tabs = Array.from(document.querySelectorAll('.view-tab'));
                const tab = tabs.find(t => t.textContent.includes('Список'));
                if (tab) {
                    tab.click();
                    return true;
                }
                return false;
            })()
            """
            switched = await eval_js(ws, switch_to_list_js)
            if not switched:
                raise Exception("Failed to click List view tab")
                
            # Wait for list container
            list_view_ready = await wait_for_element(ws, ".list-view-container", timeout=10)
            if not list_view_ready:
                raise Exception("List view container did not load")
                
            await asyncio.sleep(1)
            await capture_and_save_screenshot(ws, os.path.join(artifact_dir, "3_list_view.png"))
            
            # Switch to Table View
            print("Switching to Table view...")
            switch_to_table_js = """
            (() => {
                const tabs = Array.from(document.querySelectorAll('.view-tab'));
                const tab = tabs.find(t => t.textContent.includes('Таблиця'));
                if (tab) {
                    tab.click();
                    return true;
                }
                return false;
            })()
            """
            switched_table = await eval_js(ws, switch_to_table_js)
            if not switched_table:
                raise Exception("Failed to click Table view tab")
                
            # Wait for table container
            table_view_ready = await wait_for_element(ws, ".table-view-container", timeout=10)
            if not table_view_ready:
                # Let's fallback if the selector is different (like .table-responsive)
                table_view_ready = await wait_for_element(ws, "table", timeout=5)
                
            if not table_view_ready:
                raise Exception("Table view did not load")
                
            await asyncio.sleep(1)
            await capture_and_save_screenshot(ws, os.path.join(artifact_dir, "4_table_view.png"))
            
            # Switch back to List View to inspect task rendering & open modal
            print("Switching back to List view to open task...")
            await eval_js(ws, switch_to_list_js)
            await wait_for_element(ws, ".list-view-row.main-task", timeout=10)
            await asyncio.sleep(1)
            
            # Open task modal for 'Верстка головної сторінки'
            print("Opening task modal for 'Верстка головної сторінки'...")
            open_task_js = """
            (() => {
                const taskRows = Array.from(document.querySelectorAll('.list-view-row.main-task'));
                const taskRow = taskRows.find(r => r.querySelector('.task-title-text') && r.querySelector('.task-title-text').textContent.includes('Верстка головної сторінки'));
                if (taskRow) {
                    taskRow.click();
                    return true;
                }
                return false;
            })()
            """
            opened = await eval_js(ws, open_task_js)
            if not opened:
                raise Exception("Failed to find or click 'Верстка головної сторінки' row")
                
            # Wait for modal overlay and task details pane
            modal_ready = await wait_for_element(ws, ".modal-window.task-detail", timeout=10)
            if not modal_ready:
                raise Exception("Task modal did not render")
                
            await asyncio.sleep(1)
            await capture_and_save_screenshot(ws, os.path.join(artifact_dir, "5_task_modal_open.png"))
            
            # Check for column elements in modal and measure sizes
            modal_checks_js = """
            (() => {
                const treeCol = document.querySelector('.task-tree-sidebar');
                const detailsCol = document.querySelector('.task-details-pane');
                const commentsCol = document.querySelector('.task-comments-pane');
                
                const results = {};
                if (treeCol) {
                    const rect = treeCol.getBoundingClientRect();
                    results.tree = { width: rect.width, height: rect.height, left: rect.left, top: rect.top };
                }
                if (detailsCol) {
                    const rect = detailsCol.getBoundingClientRect();
                    results.details = { width: rect.width, height: rect.height, left: rect.left, top: rect.top };
                }
                if (commentsCol) {
                    const rect = commentsCol.getBoundingClientRect();
                    results.comments = { width: rect.width, height: rect.height, left: rect.left, top: rect.top };
                }
                
                // Check overlaps
                results.overlaps = [];
                const cols = [treeCol, detailsCol, commentsCol].filter(Boolean);
                for (let i = 0; i < cols.length; i++) {
                    for (let j = i + 1; j < cols.length; j++) {
                        const r1 = cols[i].getBoundingClientRect();
                        const r2 = cols[j].getBoundingClientRect();
                        const overlap = !(r1.right <= r2.left || r1.left >= r2.right || r1.bottom <= r2.top || r1.top >= r2.bottom);
                        if (overlap) {
                            results.overlaps.push(`Column ${i} overlaps Column ${j}`);
                        }
                    }
                }
                return results;
            })()
            """
            modal_layout = await eval_js(ws, modal_checks_js)
            print(f"Modal Layout analysis: {json.dumps(modal_layout, indent=2)}")
            
            # Upload screenshot attachment
            print("Uploading test screenshot via CDP DOM.setFileInputFiles...")
            doc = await call_cdp(ws, "DOM.getDocument")
            doc_node_id = doc["root"]["nodeId"]
            
            file_input = await call_cdp(ws, "DOM.querySelector", {
                "nodeId": doc_node_id,
                "selector": "#inlineFileUpload"
            })
            input_node_id = file_input["nodeId"]
            
            # Set the file on the input element
            await call_cdp(ws, "DOM.setFileInputFiles", {
                "nodeId": input_node_id,
                "files": [dummy_img_path]
            })
            
            # Wait for upload status spinner to appear and disappear, or wait for thumbnail
            print("Waiting for thumbnail to load...")
            thumbnail_uploaded = await wait_for_element(ws, ".attachment-thumbnail", timeout=15)
            if not thumbnail_uploaded:
                print("Thumbnail was not found. Let's wait a bit more...")
                await asyncio.sleep(5)
                thumbnail_uploaded = await wait_for_element(ws, ".attachment-thumbnail", timeout=5)
                
            await capture_and_save_screenshot(ws, os.path.join(artifact_dir, "6_screenshot_uploaded.png"))
            
            # Open Lightbox
            print("Opening Lightbox by clicking thumbnail...")
            click_thumb_js = """
            (() => {
                const thumbs = Array.from(document.querySelectorAll('.attachment-thumbnail'));
                if (thumbs.length > 0) {
                    thumbs[thumbs.length - 1].click();
                    return true;
                }
                return false;
            })()
            """
            opened_lightbox = await eval_js(ws, click_thumb_js)
            if not opened_lightbox:
                raise Exception("Failed to click image thumbnail to open lightbox")
                
            # Wait for lightbox overlay
            lightbox_ready = await wait_for_element(ws, ".lightbox-overlay", timeout=10)
            if not lightbox_ready:
                raise Exception("Lightbox overlay did not render")
                
            await asyncio.sleep(1)
            await capture_and_save_screenshot(ws, os.path.join(artifact_dir, "7_lightbox_open.png"))
            
            # Close Lightbox
            print("Closing lightbox...")
            close_lightbox_js = """
            (() => {
                const closeBtn = document.querySelector('.lightbox-close');
                if (closeBtn) {
                    closeBtn.click();
                    return true;
                }
                return false;
            })()
            """
            await eval_js(ws, close_lightbox_js)
            await asyncio.sleep(1)
            
            # Close Modal
            print("Closing task modal...")
            close_modal_js = """
            (() => {
                const closeBtn = document.querySelector('.modal-close');
                if (closeBtn) {
                    closeBtn.click();
                    return true;
                }
                return false;
            })()
            """
            await eval_js(ws, close_modal_js)
            await asyncio.sleep(1)
            
            print("Scenario simulation complete!")
            
            # Cancel the listener
            listener_task.cancel()
            await asyncio.gather(listener_task, return_exceptions=True)
            
    except Exception as e:
        print(f"Error during scenario: {e}")
        raise e
    finally:
        print("Terminating Chrome...")
        chrome_proc.terminate()
        chrome_proc.wait()
        print("Chrome terminated.")
        
        # Clean up dummy image
        if os.path.exists(dummy_img_path):
            os.remove(dummy_img_path)
            
    # Write report file
    report = {
        "modal_layout": modal_layout,
        "log_store": log_store
    }
    report_path = os.path.join(artifact_dir, "scenario_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report written to {report_path}")

if __name__ == "__main__":
    asyncio.run(run_scenario())
