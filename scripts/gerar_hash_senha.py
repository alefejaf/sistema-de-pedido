#!/usr/bin/env python3
"""Gera salt + hash de uma senha para colar na aba `usuarios` do Google Sheets.

Uso:
    python scripts/gerar_hash_senha.py

A senha é digitada de forma oculta (não aparece no terminal) e nunca é
salva em disco por este script — só o salt e o hash são impressos, para
você copiar manualmente para as colunas `salt` e `senha_hash` do usuário
na aba `usuarios` da planilha.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grade_app.auth import gerar_hash_senha, gerar_salt


def main() -> None:
    senha = getpass.getpass("Digite a senha para gerar o hash: ")
    confirmacao = getpass.getpass("Digite a senha novamente para confirmar: ")
    if senha != confirmacao:
        print("As senhas não coincidem. Nada foi gerado.")
        return
    if not senha:
        print("A senha não pode ser vazia.")
        return

    salt = gerar_salt()
    senha_hash = gerar_hash_senha(senha, salt)

    print("\nCole estes valores nas colunas correspondentes da aba 'usuarios':\n")
    print(f"salt        = {salt}")
    print(f"senha_hash  = {senha_hash}")


if __name__ == "__main__":
    main()
