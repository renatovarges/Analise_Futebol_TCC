import os
import tls_requests

# 4 dos 10 IPs grátis do Webshare (Londres, EUA-LA, EUA-Piscataway, Polônia) —
# testando vários de uma vez pra saber se é o IP específico ou o pool inteiro.
PROXIES = {
    "Londres": "http://ufzjirao:wg9po1i7d2dt@31.59.20.176:6754",
    "EUA-LA": "http://ufzjirao:wg9po1i7d2dt@198.23.243.226:6361",
    "EUA-Piscataway": "http://ufzjirao:wg9po1i7d2dt@38.154.185.97:6370",
    "Polonia": "http://ufzjirao:wg9po1i7d2dt@84.247.60.125:6095",
}

for nome, proxy in PROXIES.items():
    print(f"\n===== {nome} =====")
    try:
        r = tls_requests.get("https://api.ipify.org?format=json", proxy=proxy, timeout=15)
        print("  ping neutro:", r.status_code)
    except Exception as e:
        print("  ping neutro FALHOU:", type(e).__name__, e)
        continue
    try:
        r = tls_requests.get(
            "https://api.sofascore.com/api/v1/unique-tournament/325/season/87678/events/round/1",
            proxy=proxy, timeout=15,
        )
        print("  SofaScore:", r.status_code, "|", r.text[:150])
    except Exception as e:
        print("  SofaScore FALHOU:", type(e).__name__, e)
