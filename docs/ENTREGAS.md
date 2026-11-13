# Registro de entregas — 13/11/2026

O desenvolvimento preservou o código existente, as alterações locais e a imagem original. Não foram executadas operações mutáveis em VMs reais nem provisionamento SSH real.

| Entrega | Branch e commits | Arquivos principais | Validação local | PR |
|---|---|---|---|---|
| A/B — preservação e extração | `suporte-multiplos-extratores`: `e36675f`, `8c740f5` | `config.py`, novo `extraction.py`, `test_extraction.py`, README; normalização nos quatro arquivos já preparados pelo usuário | 20 testes iniciais; depois 38, incluindo 7-Zip e tar reais em arquivos pequenos | [#3](https://github.com/juliaexterkoetter/VMForge/pull/3) |
| C/E — proteção e validação | `protecao-maquinas-existentes`: `b3ccdb1` | novo `appliance.py`, `config.py`, `providers/virtualbox.py`, `test_protection.py` | 53 testes, proteção por UUID, XML/VDI e conflitos | [#4](https://github.com/juliaexterkoetter/VMForge/pull/4) |
| D — assistente e simulação | `melhorias-assistente-criacao`: `9d48e98` | `wizard.py`, `cli.py`, `config.py`, provedor e `test_wizard.py` | 66 testes; simulação com a imagem original/VirtualBox 7.2.22 sem alterações | [#5](https://github.com/juliaexterkoetter/VMForge/pull/5) |
| E/F — isolamento e regressões | `isolamento-imagens-importadas`: `b6b5d00`, `9658e34`, `bedf52b` | `appliance.py`, assistente/configuração, testes de isolamento e detecção | 71 testes Windows; WSL: 68 passaram, três pulados | [#6](https://github.com/juliaexterkoetter/VMForge/pull/6) |
| E — robustez SSH | `robustez-provisionamento-ssh`: `9ec8f7f` | `provisioners/kali.py`, `test_ssh.py` | 76 testes Windows; cinco novos casos de canais simulados | [#7](https://github.com/juliaexterkoetter/VMForge/pull/7) |

Os PRs #3 a #7 foram integrados com merge após aprovação dos quatro jobs Windows/Ubuntu, Python 3.12/3.14. Os detalhes da entrega de documentação/empacotamento são atualizados pelo GitHub; consulte as verificações e o relatório final da execução. Nenhum resultado de criação real foi inferido a partir de testes com mocks.

## Preservação

O arquivo não rastreado `ubprocess` continha somente a ajuda do paginador `less`. Uma cópia foi preservada fora do repositório e comparada por hash antes de removê-lo. O estado local inicial de `config.py` e seu diff também foram preservados.

Durante a primeira sincronização, atributos LF revelaram CRLF em commits antigos. A diferença foi comprovada como somente quebras de linha, preservada em stash, e o fast-forward foi feito sem descartar conteúdo. Esse stash de preservação foi mantido; não representa uma funcionalidade pendente.

## Problemas encontrados nos testes e resolvidos

- O manifesto 7-Zip Windows apresenta separadores invertidos. A primeira integração recusou-os; a normalização passou a ocorrer antes da validação de caminhos, mantendo o bloqueio de traversal/UNC/unidades.
- Um teste de detecção dependia do PATH real no WSL. A busca passou a ser simulada explicitamente.
- O XML real utiliza namespace padrão do VirtualBox; a gravação agora o preserva e os fixtures usam namespace.

## Limites da evidência

Os testes de extração usam arquivos pequenos; os testes de VDI usam cabeçalhos sintéticos e verificam invariantes, não um sistema operacional inicializável. A imagem original foi apenas inspecionada em leitura: manifesto e XML de 3011 bytes em memória. O VDI de 16828924928 bytes não foi extraído nesta validação.

A origem é mantida em leitura e a cópia recebe identidades novas. O código de mudança de UUID depende do layout VDI 1.1 e foi conferido no [código oficial](https://github.com/VirtualBox/virtualbox/blob/main/src/VBox/Storage/VDICore.h). Não há suporte a discos diferenciais, cadeia de snapshots ou importação direta de `.vbox`.

Criação real, boot, Guest Additions, SSH, atualizações, snapshot e avaliação prática com NVDA continuam sendo validações separadas. A versão permanece candidata até concluir essas verificações com autorização do usuário.
