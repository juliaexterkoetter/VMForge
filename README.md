# VMForge

CLI em português para preparar uma **nova VM Kali Linux no Oracle VirtualBox**, com interface textual, menus numerados e operação pelo teclado.

**Estado: candidato 0.2.0rc1.** Testes automatizados, extração de arquivos pequenos e simulação foram validados. A criação real ponta a ponta e a avaliação manual com NVDA ainda estão pendentes. Não trate esta versão como certificada para produção.

## Requisitos e instalação

- Windows 11 é o ambiente principal para criação; testes também rodam no Ubuntu.
- Python 3.12 ou 3.14, Oracle VirtualBox 7.2 e 7-Zip com interface de linha de comando.
- Imagem original `.7z` do Kali para VirtualBox, com Guest Additions e conta inicial `kali`.
- Espaço para o conteúdo descompactado mais 512 MiB de margem. O assistente informa os valores antes de criar arquivos.
- Internet dentro da VM apenas se o provisionamento SSH ou atualizações forem selecionados.

Verifique a procedência e o checksum da imagem pelo [site oficial do Kali](https://www.kali.org/get-kali/). A extensão e o nome do arquivo não provam autenticidade. O VMForge ainda não consulta checksums oficiais automaticamente.

Instale em ambiente virtual, dentro da pasta do projeto:

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -B -m vmforge create --dry-run
```

Git Bash no Windows:

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -B -m vmforge create --dry-run
```

Não é necessário ativar o ambiente nem alterar a política do PowerShell. Use o mesmo Python do ambiente virtual nos comandos abaixo. Para Ubuntu, o executável correspondente é `.venv/bin/python`.

## Assistente e simulação

```text
python -B -m vmforge create --dry-run
python -m vmforge create
```

O assistente solicita a imagem, um destino inexistente, o nome da VM e o modo básico ou avançado. O básico usa 4096 MB, 2 CPUs, NAT e uma porta local disponível a partir de 2223. O avançado permite escolher recursos, porta e NAT ou rede desconectada.

Antes da confirmação são escolhidos: início da VM, configuração SSH, pastas de laboratório, atualização de pacotes, snapshot e estado final ligado/desligado. Pastas, atualização e snapshot são opcionais. O plano completo aparece antes da autorização. Uma resposta negativa cancela sem criar arquivos ou VMs. Senhas só são solicitadas na execução autorizada, antes da preparação da imagem.

`--dry-run` verifica a assinatura e o manifesto, o espaço disponível, destino, nome e portas; consulta VMs registradas se o VirtualBox estiver disponível. Não extrai, registra, configura, inicia ou provisiona. Sem VirtualBox, avisa que os conflitos de registro não foram verificados. XML e VDI são validados após a extração autorizada. Use `-B` para impedir também arquivos de cache do próprio interpretador Python.

Na execução, a cópia recebe UUIDs de máquina/disco e MACs independentes antes do registro. O fluxo usa o UUID validado, e não uma comparação de listas para escolher a máquina. Se solicitado, configura SSH, verifica a chave de host lida por Guest Additions e troca a senha. O snapshot `VMForge-Inicial` é criado somente depois de confirmar o desligamento. Não há desligamento forçado.

Se SSH não for configurado, a senha original da imagem não será alterada. O resumo informa essa condição. Acesso após provisionamento, com a VM ligada:

```text
ssh -p 2223 kali@127.0.0.1
```

## Comandos

| Comando após `python -m vmforge` | Função |
|---|---|
| sem argumentos | Menu textual |
| `check` | Consulta Python e VirtualBox |
| `list` | Lista nome e UUID das VMs |
| `status NOME_OU_UUID` | Consulta estado |
| `create --dry-run` | Mostra o plano sem executar |
| `create` | Assistente com confirmação explícita |
| `start NOME_OU_UUID` | Inicia em modo headless |
| `stop NOME_OU_UUID` | Solicita desligamento ACPI após confirmação |
| `snapshot NOME_OU_UUID TITULO` | Cria snapshot com VM desligada, após confirmação |

## Extração e segurança

O **7-Zip é obrigatório para validar o manifesto**, mesmo quando o tar faz a extração. No Windows, o `tar.exe` nativo de `System32` tem preferência para ler o conteúdo. O tar do Git Bash não é selecionado. O 7-Zip instalado em Program Files é preferido ao PATH e sua interface é verificada.

O manifesto deve conter somente diretórios, `.vbox` e `.vdi`: até 128 entradas e 128 GiB descompactados. A preparação exige exatamente um `.vbox` e um VDI independente. Caminhos absolutos, traversal, UNC, unidades Windows, nomes reservados, colisões e links identificados no manifesto são recusados antes da extração. Entradas criptografadas não são aceitas.

Cada arquivo é recebido por stdout, com limite de tamanho e tempo, e gravado pelo Python com criação exclusiva. O extrator não escolhe os caminhos de saída. A origem é aberta somente para leitura; um destino existente nunca é reutilizado. Falhas durante a extração removem somente o destino novo criado pela chamada. Falhas posteriores preservam os arquivos para diagnóstico e não são anunciadas como conclusão.

O XML não aceita entidades/DTD, referências externas, snapshots existentes, discos diferenciais, pastas compartilhadas ou mídias externas. O cabeçalho VDI e sua identidade são verificados; isso não verifica o sistema de arquivos do convidado. A geração de nova identidade altera apenas a cópia recém-extraída. O layout VDI 1.1 foi conferido no [código oficial do VirtualBox](https://github.com/VirtualBox/virtualbox/blob/main/src/VBox/Storage/VDICore.h).

**WinRAR não tem adaptador validado neste projeto.** WinRAR, Rar.exe e UnRAR.exe não são utilizados automaticamente para `.7z`; código de retorno de uma interface gráfica não comprova extração. Importação direta de `.vbox` permanece bloqueada. Use o arquivo `.7z` original.

A pasta de destino deve ser privada, sem outros processos alterando-a durante a execução. O programa não é uma sandbox para executáveis comprometidos e não impõe cotas de memória ao extrator. Os limites de tamanho não substituem a confiança na ferramenta e na origem.

## Preservação de máquinas existentes

As máquinas e portas protegidas são definidas em [configuração local de proteção](docs/PROTECAO_LOCAL.md). Antes de utilizar comandos de alteração, crie o arquivo de configuração particular. A ausência de uma configuração válida bloqueia operações que dependem dessa proteção.


O VMForge possui proteções para evitar alterações acidentais em máquinas virtuais preexistentes. Operações mutáveis consultam o UUID, inclusive se a VM foi renomeada. O assistente evita portas reservadas para máquinas protegidas. Nunca selecione os arquivos ou diretórios dessa VM como destino.

Conflitos de nome, UUID de máquina, UUID de disco e regras NAT são recusados. Portas de VMs desligadas também são consideradas. Não há exclusão automática de VMs nem rollback destrutivo. Se uma etapa falhar depois do registro, consulte `list` e `status`, preserve o diagnóstico e não repita a criação no mesmo destino.

Senhas novas não são argumentos de processos. O bootstrap usa a senha pública inicial da imagem apenas no convidado. A autenticação por Guest Additions usa arquivo temporário de credencial, removido ao terminar. O SSH é vinculado a `127.0.0.1` e verifica a chave do convidado. Não publique imagens, chaves, senhas ou arquivos pessoais no repositório.

## Testes e empacotamento

```text
python -B -m unittest discover -s tests -v
python -m compileall -q vmforge
python -m pip wheel --no-deps --wheel-dir dist .
```

Os testes de integração criam arquivos 7z pequenos em pastas temporárias. Não criam nem usam VMs. Testes específicos do tar são executados no Windows; integração com 7-Zip é sinalizada como pulada se a ferramenta não existir. A CI exige que o 7-Zip esteja disponível e executa a matriz Windows/Ubuntu com Python 3.12/3.14, empacotamento e instalação do wheel em ambiente isolado.

Para testar o pacote instalado fora do checkout:

```text
python -m venv work/test-package
```

Instale o wheel nesse ambiente e execute `python -I -m vmforge --version`, usando o Python do ambiente. A CI faz essa verificação automaticamente.

## Acessibilidade e solução de problemas

- Interface textual, sem animações, cores obrigatórias ou dependência gráfica. Menus e confirmações funcionam pelo teclado. A avaliação prática com NVDA ainda precisa ser feita pelo usuário.
- Se `vmforge` não estiver no PATH, use `python -m vmforge` com o Python correto.
- Se acentos saírem incorretos em redirecionamentos, use `$env:PYTHONIOENCODING='utf-8'` no PowerShell ou `export PYTHONIOENCODING=utf-8` no Git Bash. `getpass` precisa de terminal interativo para ocultar a senha.
- Se aparecer “7-Zip compatível não encontrado”, instale o 7-Zip oficial e confirme `7z i`; WinRAR sozinho não satisfaz o requisito.
- Se uma imagem for recusada por referência externa ou formato, não contorne a validação editando a VM existente. Use uma imagem original compatível.
- Se houver timeout de Guest Additions/SSH, a VM fica preservada para diagnóstico. Não há garantia de retomada automática.
- Atualizações podem demorar e exigir um boot posterior para ativar um novo kernel. Aplicativos gráficos do Kali precisam de avaliação de acessibilidade separada.

Consulte [o roadmap](docs/ROADMAP.md) e [o registro de entregas](docs/ENTREGAS.md). Não há afiliação com Oracle ou Kali Linux.

## Direitos autorais

Copyright © 2026 Júlia Schaden Exterkoetter. Todos os direitos reservados.

Este repositório é público para apresentação e consulta do código-fonte. Não é concedida autorização geral para utilizar, copiar, modificar ou redistribuir o software. Consulte [COPYRIGHT.md](COPYRIGHT.md).
