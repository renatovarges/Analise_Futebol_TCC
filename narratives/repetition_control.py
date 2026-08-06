"""
narratives/repetition_control.py — controle de repetição na rodada (seção 6).

O motor Python (_redigir_python) já varia a abertura por seed própria de
cada time, mas cada seed é independente — nada impede que Flamengo e
Palmeiras caiam no mesmo molde por acaso. Este módulo olha a RODADA INTEIRA
(até 40 parágrafos: 20 times × 2 eixos) e sinaliza repetição entre eles.

Precisão factual sempre vence variedade (seção 6 da revisão): este módulo
SINALIZA, não reescreve — quem chama decide se troca de sentença/seed ou
aceita a repetição pontual.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
LIMIAR_SIMILARIDADE = 0.72


def _normalizar_estrutura(texto: str, nomes: tuple[str, ...]) -> str:
    """Substitui números e nomes de clube por marcadores — sobra só o esqueleto da frase."""
    t = texto
    for nome in nomes:
        if nome:
            t = t.replace(nome, "#TIME#")
    t = _NUM_RE.sub("#N#", t)
    return t.lower()


def _abertura(texto: str, n_palavras: int = 4) -> str:
    palavras = texto.strip().split()[:n_palavras]
    return " ".join(w.lower().strip(".,;:") for w in palavras)


def _verbo_principal(texto: str) -> str:
    palavras = texto.strip().split()
    return palavras[0].lower().strip(".,;:") if palavras else ""


@dataclass
class ControleRepeticao:
    max_repeticoes_verbo: int = 3   # numa rodada de ~20 times, até 3 usos do mesmo verbo é aceitável
    _aberturas: list[str] = field(default_factory=list)
    _verbos: list[str] = field(default_factory=list)
    _estruturas: list[str] = field(default_factory=list)
    _chaves: list[str] = field(default_factory=list)

    def checar(self, chave: str, texto: str, time: str, adversario: str) -> list[str]:
        problemas = []
        abertura = _abertura(texto)
        if abertura in self._aberturas:
            outra = self._chaves[self._aberturas.index(abertura)]
            problemas.append(f"abertura repetida ({abertura!r}), já usada em {outra!r}")

        verbo = _verbo_principal(texto)
        usos = self._verbos.count(verbo)
        if verbo and usos >= self.max_repeticoes_verbo:
            problemas.append(f"verbo de abertura {verbo!r} já usado {usos}x na rodada")

        estrutura = _normalizar_estrutura(texto, (time, adversario))
        for i, anterior in enumerate(self._estruturas):
            sim = SequenceMatcher(None, estrutura, anterior).ratio()
            if sim >= LIMIAR_SIMILARIDADE:
                problemas.append(
                    f"estrutura quase idêntica a {self._chaves[i]!r} (similaridade {sim:.2f})"
                )
                break
        return problemas

    def registrar(self, chave: str, texto: str, time: str, adversario: str) -> None:
        self._aberturas.append(_abertura(texto))
        self._verbos.append(_verbo_principal(texto))
        self._estruturas.append(_normalizar_estrutura(texto, (time, adversario)))
        self._chaves.append(chave)

    def reset(self) -> None:
        self._aberturas.clear()
        self._verbos.clear()
        self._estruturas.clear()
        self._chaves.clear()
