import os

proxy = os.environ.get("SOFASCORE_PROXY")
print("SOFASCORE_PROXY setada?", bool(proxy), "| tamanho:", len(proxy) if proxy else 0)

print("\n=== 1) qual IP o tls_requests reporta, via proxy, num site neutro? ===")
try:
    import tls_requests
    r = tls_requests.get("https://api.ipify.org?format=json", proxy=proxy, timeout=15)
    print("status:", r.status_code, "| corpo:", r.text[:200])
except Exception as e:
    print("FALHOU:", type(e).__name__, e)

print("\n=== 2) tls_requests direto no SofaScore, via proxy ===")
try:
    import tls_requests
    r = tls_requests.get(
        "https://api.sofascore.com/api/v1/unique-tournament/325/season/87678/events/round/1",
        proxy=proxy, timeout=15,
    )
    print("status:", r.status_code, "| corpo:", r.text[:300])
except Exception as e:
    print("FALHOU:", type(e).__name__, e)

print("\n=== 3) requests (biblioteca comum, sem spoof de TLS) via proxy, mesmo IP? ===")
try:
    import requests
    r = requests.get("https://api.ipify.org?format=json", proxies={"http": proxy, "https": proxy}, timeout=15)
    print("status:", r.status_code, "| corpo:", r.text[:200])
except Exception as e:
    print("FALHOU:", type(e).__name__, e)

print("\n=== 4) requests direto no SofaScore, via proxy ===")
try:
    import requests
    r = requests.get(
        "https://api.sofascore.com/api/v1/unique-tournament/325/season/87678/events/round/1",
        proxies={"http": proxy, "https": proxy}, timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    print("status:", r.status_code, "| corpo:", r.text[:300])
except Exception as e:
    print("FALHOU:", type(e).__name__, e)
