import json
import httpx
from BOT.tools.proxy import get_proxy
from BOT.Charge.Shopify.slf.api import autoshopify

def get_site(user_id):
    with open("DATA/sites.json", "r") as f:
        sites = json.load(f)
    return sites.get(str(user_id), {}).get("site")

async def check_card(user_id, cc, site=None):
    if not site:
        site = get_site(user_id)
    if not site:
        return "Site Not Found"

    proxy = get_proxy(user_id)
    
    retries = 0
    max_retries = 3
    
    while retries < max_retries:
        try:
            # Create session with proxy if available
            # httpx uses 'proxy' parameter (single proxy for all)
            if proxy:
                async with httpx.AsyncClient(
                    timeout=60.0,
                    proxy=proxy,
                    verify=False,
                    follow_redirects=True
                ) as session:
                    result = await autoshopify(site, cc, session)
            else:
                async with httpx.AsyncClient(
                    timeout=60.0,
                    verify=False,
                    follow_redirects=True
                ) as session:
                    result = await autoshopify(site, cc, session)
            
            response_text = result.get("Response", "UNKNOWN")
            
            # Check for connection errors that need retry
            if any(x in response_text.upper() for x in [
                "SERVER DISCONNECTED", 
                "INCOMPLETE CHUNKED", 
                "CONNECTION ERROR",
                "TIMEOUT"
            ]):
                retries += 1
                continue
            
            # Return the response
            return response_text
            
        except httpx.TimeoutException:
            retries += 1
            if retries >= max_retries:
                return "Request Timeout"
            continue
        
        except httpx.ProxyError as e:
            return f"Proxy Error: {str(e)[:50]}"
        
        except httpx.ConnectError as e:
            retries += 1
            if retries >= max_retries:
                return f"Connect Error: {str(e)[:50]}"
            continue
            
        except Exception as e:
            return f"Error: {str(e)[:80]}"
    
    return "Connection Failed - Check Proxy/Network"
