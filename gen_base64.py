import os
import base64
from pathlib import Path

base_dir = Path(r"C:\Users\User\.gemini\antigravity\scratch\Analise_Futebol_TCC")
assets_dir = base_dir / "assets"
output_file = base_dir / "image_data.py"

def get_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

print("Gerando banco de dados de imagens em Base64...")

content = "IMAGES = {\n"

# Logos
for img in (assets_dir / "logos").glob("*.png"):
    content += f'    "logo_{img.stem}": "{get_base64(img)}",\n'

# Teams
for img in (assets_dir / "teams").glob("*.png"):
    content += f'    "team_{img.stem}": "{get_base64(img)}",\n'

content += "}\n"

with open(output_file, "w") as f:
    f.write(content)

print(f"Sucesso! Banco de dados criado em {output_file}")
