# Continuação de provisionamento

O comando `python -B -m vmforge resume-provision` retoma exclusivamente a etapa SSH
em uma VM de teste já registrada, sem extrair ou registrar uma segunda VM.

Requisitos: VM ligada, nome prefixado `VMForge-`, UUID da máquina e do VDI
coincidentes com os argumentos, arquivo `.vbox` igual ao configurado no
VirtualBox, pasta sem links e regra NAT local configurada para a porta esperada.

Execute primeiro com `--dry-run`. A execução real depende das credenciais
padrão de uma imagem Kali **ainda não provisionada**. Caso a senha inicial já
tenha sido trocada, a operação falha de forma conservadora. Não repita após
falha de etapa sem verificar o estado. A nova senha é solicitada por `getpass`
no console nativo do Windows; nunca a passe por argumento.

O comando cria o snapshot `VMForge-Inicial` somente depois de autenticar com
a nova senha via SSH e desligar normalmente a VM. Não força o desligamento.

## Privacidade dos diagnósticos

Não salve `VBoxManage showvminfo` completo em relatórios públicos: campos de
descrição podem incluir credenciais padrão. Prefira campos estritamente
necessários (`UUID`, `VMState`, `CfgFile`, `nic1`, `Forwarding`, etc.).
Não grave senhas nem chaves privadas em logs, commits, issues ou PRs.
Antes de compartilhar relatórios, revise e oculte dados pessoais.
