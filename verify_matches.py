import pandas as pd
from graphic_renderer import get_team_logo_path, IMAGES

# List of teams from the spreadsheet check
teams = ['Vitória', 'Coritiba', 'Internacional', 'Atlético Mineiro', 'Fluminense', 'Chapecoense', 'Corinthians', 'São Paulo', 'Mirassol', 'Botafogo', 'Flamengo', 'RB Bragantino', 'Santos', 'Remo', 'Palmeiras', 'Grêmio', 'Bahia', 'Vasco da Gama', 'Cruzeiro', 'Athletico Paranaense']

print("=== TESTE DE MATCH DE ESCUDOS ===")
for team in teams:
    path = get_team_logo_path(team)
    if path in IMAGES:
        print(f"[OK] {team:25} -> {path}")
    else:
        print(f"[ERRO] {team:25} -> {path} (NÃO ENCONTRADO NO DB)")
