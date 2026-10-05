"""
scripts/atualizar_e_publicar.py — atualização de viagem.

Faz o mesmo que o botão "Atualizar dados da API" da interface (busca os jogos
mais recentes no FotMob), mas rodando localmente — de qualquer rede normal
(casa, hotel, wifi de aeroporto, hotspot do celular) — e publica o resultado
para o site no Streamlit Cloud.

Ao final, se algo mudou no cache local, cria um commit e envia (git push)
para o GitHub — o site publicado passa a refletir os dados assim que reiniciar
o cache de 1 hora.

Uso:
    python scripts/atualizar_e_publicar.py
"""
from __future__ import annotations

import subprocess
import sys
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True)


def main() -> None:
    print("=" * 70)
    print("Buscando dados atualizados no FotMob...")
    print("=" * 70)

    from fotmob_api import atualizar_temporada, _arquivo_cache

    cache = _arquivo_cache().relative_to(BASE_DIR).as_posix()

    try:
        jogos = atualizar_temporada()
    except Exception as e:
        print(f"\n[ERRO] {e}")
        print(
            "\nO FotMob pode estar fora do ar ou a rede pode estar instável. "
            "O que já foi baixado ficou salvo — tente novamente em alguns minutos."
        )
        sys.exit(1)

    completos = sum(1 for j in jogos if j["status"] == "complete")
    print(f"\n{len(jogos)} partidas na base ({completos} completas).")

    status = _git("status", "--porcelain", cache)
    if not status.stdout.strip():
        print("\nNenhuma mudança nova em relação ao GitHub — nada para publicar.")
        return

    print("\nPublicando no GitHub...")
    _git("add", cache)
    commit = _git("commit", "-m", "chore: atualiza cache de dados do FotMob")
    print(commit.stdout.strip() or commit.stderr.strip())
    if commit.returncode != 0:
        print("\n[ERRO] Falha ao criar o commit.")
        sys.exit(1)

    push = _git("push")
    print(push.stdout.strip() or push.stderr.strip())
    if push.returncode != 0:
        print(
            "\n[ERRO] O commit foi criado localmente, mas o push falhou "
            "(confira sua conexão ou credenciais do GitHub). Rode 'git push' "
            "manualmente quando puder."
        )
        sys.exit(1)

    print("\nPronto! O site publicado vai refletir esses dados em até 1 hora "
          "(cache), ou imediatamente se você reiniciar o app no Streamlit Cloud.")


if __name__ == "__main__":
    main()
