import json
import requests
import os
import time

def main():
    creds_path = ".greennode.json"
    if not os.path.exists(creds_path):
        print("ERROR: .greennode.json not found")
        return
    
    with open(creds_path, "r") as f:
        creds = json.load(f)
        
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    
    print("Authenticating with VNG Cloud IAM...")
    iam_url = "https://iam.api.vngcloud.vn/accounts-api/v2/auth/token"
    payload = "grant_type=client_credentials"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    try:
        # Authenticate
        response = requests.post(
            iam_url, 
            data=payload, 
            headers=headers, 
            auth=(client_id, client_secret),
            timeout=15
        )
        if response.status_code != 200:
            print(f"Failed to authenticate: {response.text}")
            return
        
        access_token = response.json().get("access_token")
        print("Successfully authenticated with IAM!")
        
        # 1. Fetch CR Credentials for Image Auth
        print("Fetching Container Registry credentials...")
        cred_url = "https://agentbase.api.vngcloud.vn/cr/api/v1/registry-credential"
        rep_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        cred_res = requests.get(cred_url, headers=rep_headers, timeout=15)
        if cred_res.status_code != 200:
            print("Failed to fetch registry credentials:", cred_res.text)
            return
        
        cred_data = cred_res.json()
        reg_user = cred_data.get("username")
        reg_pass = cred_data.get("secret")
        
        # 2. Update Runtime
        runtime_id = "runtime-8c576506-7160-41ee-aea3-516f5d5aa85f"
        image_url = "vcr.vngcloud.vn/111480-abp112154/sysmon-agent:latest"
        flavor_id = "runtime-s2-general-2x4"
        
        # Read API key from local config
        config_path = "data/config.json"
        maas_api_key = ""
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                maas_api_key = config_data.get("api_key")
        
        if not maas_api_key:
            print("ERROR: MAAS_API_KEY not found in data/config.json")
            return
            
        print(f"\nTriggering runtime update for ID: {runtime_id}...")
        update_url = f"https://agentbase.api.vngcloud.vn/runtime/agent-runtimes/{runtime_id}"
        
        payload = {
            "imageUrl": image_url,
            "flavorId": flavor_id,
            "description": "SysMon Agent - 24/7 System Monitoring",
            "command": [],
            "args": [],
            "environmentVariables": {
                "MAAS_API_KEY": maas_api_key
            },
            "autoscaling": {
                "minReplicas": 1,
                "maxReplicas": 1,
                "cpuUtilization": 50,
                "memoryUtilization": 50
            },
            "imageAuth": {
                "enabled": True,
                "username": reg_user,
                "password": reg_pass
            }
        }
        
        update_res = requests.patch(update_url, json=payload, headers=rep_headers, timeout=15)
        print("Update Response Status Code:", update_res.status_code)
        if update_res.status_code not in [200, 202]:
            print("Failed to update runtime:", update_res.text)
            return
            
        print("Update request accepted. Dynamic update is in progress.")
        
        # 3. Poll Status
        print("\nPolling runtime status (waiting for ACTIVE)...")
        max_attempts = 30 # 30 * 10 seconds = 300 seconds (5 minutes)
        current_status = ""
        version = None
        
        for attempt in range(1, max_attempts + 1):
            get_res = requests.get(update_url, headers=rep_headers, timeout=15)
            if get_res.status_code == 200:
                runtime_data = get_res.json()
                current_status = runtime_data.get("status")
                print(f"Attempt {attempt}/{max_attempts}: Status is {current_status}")
                
                if current_status == "ACTIVE":
                    print("Runtime is now ACTIVE!")
                    break
                elif current_status in ["ERROR", "FAILED", "UPDATE_ERROR"]:
                    print("Runtime failed with status:", current_status)
                    print("Status Reason:", runtime_data.get("statusReason"))
                    return
            else:
                print(f"Failed to fetch status (HTTP {get_res.status_code}): {get_res.text}")
                
            time.sleep(10)
        else:
            print("Timed out waiting for runtime to become ACTIVE.")
            return
            
        # 4. Check/Create Endpoint
        print("\nChecking endpoints...")
        endpoints_url = f"https://agentbase.api.vngcloud.vn/runtime/agent-runtimes/{runtime_id}/endpoints"
        ep_res = requests.get(endpoints_url, headers=rep_headers, timeout=15)
        
        endpoints = []
        if ep_res.status_code == 200:
            endpoints = ep_res.json().get("listData", [])
            print(f"Found {len(endpoints)} endpoints.")
        else:
            print("Failed to list endpoints:", ep_res.text)
            
        target_endpoint_url = ""
        
        if not endpoints:
            print("No endpoints found. Creating a new endpoint...")
            ep_payload = {
                "name": "default"
            }
            create_ep_res = requests.post(endpoints_url, json=ep_payload, headers=rep_headers, timeout=15)
            print("Create Endpoint Status Code:", create_ep_res.status_code)
            if create_ep_res.status_code in [200, 201, 202]:
                ep_data = create_ep_res.json()
                print("Endpoint created successfully:")
                print(json.dumps(ep_data, indent=2))
                target_endpoint_url = ep_data.get("url")
            else:
                print("Failed to create endpoint:", create_ep_res.text)
        else:
            # Look for an endpoint named 'default' or take the first one
            default_ep = next((ep for ep in endpoints if ep.get("name") == "default"), endpoints[0])
            target_endpoint_url = default_ep.get("url")
            print("Using existing endpoint details:")
            print(json.dumps(default_ep, indent=2))
            
        print("\n================ DEPLOYMENT SUMMARY ================")
        print(f"Runtime Name: my-agent")
        print(f"Runtime ID:   {runtime_id}")
        print(f"Status:       ACTIVE")
        print(f"Public URL:   {target_endpoint_url}")
        print(f"Health Check: {target_endpoint_url}/health")
        print("====================================================\n")
        
    except Exception as e:
        print("An error occurred during deployment:", str(e))

if __name__ == "__main__":
    main()
