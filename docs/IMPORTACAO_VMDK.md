# VMForge: primeira evolução para discos VMDK

Este pacote **não modifica a VM Kali nem a Metasploitable que já existem**. Ele adiciona um módulo experimental para importar **uma terceira VM nova** a partir de um VMDK confiável. A interface do comando principal `vmforge` ainda não foi alterada.

## Como incorporar no repositório

Copie `vmforge/import_disk.py` para a pasta `vmforge/` do repositório VMForge. Copie `tests/test_import_disk.py` para `tests/`.

No Git Bash, na raiz do repositório, crie uma branch antes de copiar:

```bash
git switch -c feature/import-vmdk-hostonly
```

Depois execute os testes locais:

```bash
./.venv/Scripts/python.exe -B -m unittest discover -s tests -v
./.venv/Scripts/python.exe -B -m vmforge.import_disk --help
```

A importação exige o arquivo de proteção local `~/.vmforge/config.json` definido em `docs/PROTECAO_LOCAL.md`. Cadastre por UUID **ambas as VMs existentes** como protegidas antes de qualquer execução real. Nunca compartilhe o arquivo privado.

## Simulação (não cria nada)

No Git Bash, usando caminhos com barras normais ou caminhos Windows entre aspas:

```bash
./.venv/Scripts/python.exe -B -m vmforge.import_disk \
  --source 'C:\Laboratorios\Maquinas-Virtuais\Metasploitable2\Metasploitable2-Linux\Metasploitable.vmdk' \
  --name Metasploitable2-TESTE \
  --basefolder 'C:\Laboratorios\Maquinas-Virtuais' \
  --hostonly 'VirtualBox Host-Only Ethernet Adapter'
```

Não use `--execute` até que os testes passem e o plano exibido seja revisado. A execução real exige a flag `--execute` **e** a confirmação `CRIAR`. O programa cria somente uma VM nova, com clone de disco VDI independente, uma placa Host-only, 512 MB e 1 CPU, e a deixa desligada. A origem permanece intacta.

**Não use o nome `Metasploitable2` nem o nome da Kali existente:** o módulo recusa uma VM já registrada. A máquina intencionalmente vulnerável deve permanecer só em Host-only, sem NAT ou Bridge. Se ocorrer falha após o registro, ele preserva o estado parcial para diagnóstico, sem tentar excluir ou refazer automaticamente.

## Limitações

- Código novo passou por checagem de sintaxe, mas ainda precisa dos testes completos contra o código do repositório e da validação real no Windows com VirtualBox 7.2.
- O módulo é experimental e não foi conectado ao menu principal `vmforge`.
- O carregamento de VMDK originado de fonte não confiável não é seguro; verifique procedência e integridade.
- O módulo não gerencia DHCP nem importa redes automaticamente: a Host-only deve existir.
- O módulo não executa exploração nem altera snapshots das VMs atuais.
