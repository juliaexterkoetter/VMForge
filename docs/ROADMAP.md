# Roadmap VMForge

## Candidato 0.2.0rc1

Implementado e coberto por testes:

- CLI textual em português e confirmações explícitas.
- Plano completo e modo `create --dry-run`.
- Extração 7z com manifesto validado, caminhos controlados e limites.
- 7-Zip e tar nativo no Windows, inclusive caminhos com espaços e Unicode.
- Isolamento de identidade na cópia nova e bloqueio por UUID protegido.
- Validação conservadora de XML e cabeçalho VDI.
- Início opcional, rede NAT/desconectada, opções de SSH, pastas, atualização e snapshot.
- SSH com chave de host verificada e consumo limitado das duas saídas.
- CI Windows/Ubuntu, Python 3.12/3.14, wheel e instalação isolada.

Ainda necessário antes de declarar a primeira versão estável:

- Criação real de uma VM nova no Windows, somente com autorização explícita.
- Verificação real de boot, Guest Additions, SSH, senha, pastas, atualização e snapshot.
- Avaliação manual de acessibilidade com NVDA no PowerShell e Git Bash.

## Evolução posterior

- Retomada de instalações interrompidas com registro persistente de etapas.
- Checksum oficial autenticado da imagem original.
- Importação segura direta de `.vbox`, atualmente bloqueada.
- Limites de memória/CPU impostos ao extrator pelo sistema operacional.
- Mais formatos de disco, convidados e provedores.
- Criação real em Linux/macOS, ainda não validada.
- Presets de laboratórios e verificação de ferramentas específicas.

Não há exclusão automática de VMs nem recuperação destrutiva.
