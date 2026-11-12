# VMForge

**VMForge — Virtual Machine Automation Toolkit**

Ferramenta de linha de comando em Python que automatiza a criação de um laboratório Kali Linux a partir da **imagem oficial pré-configurada para Oracle VirtualBox**. A interface é textual, utilizável com teclado e foi pensada para funcionar com leitores de tela como o NVDA.

**Estado: v0.1.1 — protótipo funcional, ainda não validado em uma instalação ponta a ponta.** Os comandos de leitura e testes unitários foram verificados em ambiente de desenvolvimento. Teste a criação em uma imagem **nova**, isolada, antes de recomendar a outros usuários. Não é um instalador universal de qualquer VM.

## Pré-requisitos

- Windows 11 com Python 3.10+ (desenvolvido para VirtualBox 7.2; outras versões não verificadas).
- Oracle VirtualBox com `VBoxManage`.
- 7-Zip instalado para extrair `.7z` (não é necessário para `.vbox`).
- Imagem oficial *Virtual Machines → VirtualBox* do Kali Linux: https://www.kali.org/get-kali/
- A imagem deverá incluir as VirtualBox Guest Additions e usar credenciais **iniciais** `kali` / `kali`, padrão das imagens oficiais.
- Capacidade de virtualização habilitada e recursos suficientes de RAM e disco.
- Acesso à internet dentro da VM para instalar/ativar o OpenSSH.

## Instalação

No PowerShell ou Git Bash dentro da pasta do projeto:

```shell
python -m pip install --user -e .
```

Depois:

```shell
vmforge --help
vmforge check
vmforge list
vmforge create
```

Se o executável `vmforge` ainda não estiver no PATH, execute `python -m vmforge create` ou reinicie o terminal após configurar a pasta Scripts do Python no PATH.

No Windows, também existe `scripts/install-windows.ps1`, que utiliza `pip install --user -e .`.

## Assistente (`vmforge create`)

1. Solicita o caminho de um `.7z` ou `.vbox` **de uma imagem nova do Kali**.
2. Solicita uma **nova pasta de destino**, ainda inexistente, e RAM/CPUs/porta SSH.
3. Copia ou extrai o conteúdo; procura um `.vbox` e registra a VM.
4. Configura NAT e encaminhamento da porta SSH para `127.0.0.1` (somente acesso local).
5. Inicia a VM em modo headless; usa Guest Additions para habilitar o SSH.
6. Verifica a chave SSH do próprio convidado antes de conectar por SSH; pede uma nova senha sem eco de caracteres e muda a senha da conta `kali` pelo canal SSH.
7. Cria as pastas `scans`, `evidencias` e `notas`; oferece atualização completa opcional.
8. Desliga a VM pelo Linux, aguarda e cria o snapshot `VMForge-Lab-Preparado`; pergunta se deseja religá-la.

Resultado: `ssh -p 2222 kali@127.0.0.1` (ou porta personalizada).

**Atenção:** a primeira versão **não verifica automaticamente** todas as ferramentas do professor ou instala componentes gráficos adicionais. Ela prepara a base e permite que o usuário complete a verificação do laboratório. É intencional para evitar instalar pacotes incompatíveis em qualquer imagem não testada.

## Comandos

| Comando | Uso |
|---|---|
| `vmforge` | Menu textual |
| `vmforge check` | Verifica Python e VirtualBox |
| `vmforge list` | Lista VMs cadastradas |
| `vmforge status NOME` | Consulta estado de uma VM |
| `vmforge start NOME` | Inicia VM em modo headless |
| `vmforge stop NOME` | Solicita desligamento ACPI (não força) |
| `vmforge snapshot NOME TITULO` | Snapshot com VM desligada |
| `vmforge create` | Assistente de criação Kali VirtualBox |

## Segurança

- **Não rode `create` na VM existente do MBA.** A ferramenta exige pasta de destino nova, não remove VMs antigas, mas importar uma cópia de uma VM registrada pode gerar conflito de UUID no VirtualBox. Use um `.7z` oficial novo, ainda não importado, para testar.
- A senha inicial `kali` é **pública e temporária** na imagem oficial. Ela é usada uma vez para habilitar o SSH. O texto `kali` aparece no comando de bootstrap dentro do convidado. **Senhas novas nunca são colocadas em argumentos de processos**: são transferidas através de SSH criptografado, e `getpass` oculta a digitação.
- O `guestcontrol` usa um arquivo temporário local para a credencial de login inicial. Esse arquivo é removido ao final. Em máquinas compartilhadas, arquivos temporários podem ter riscos residuais; recomenda-se testar em máquina confiável.
- SSH fica ligado apenas a `127.0.0.1`, e o cliente verifica se a chave SSH apresentada corresponde à chave pública lida na VM via Guest Additions.
- Não usa `shell=True` no host para chamar o `VBoxManage`.
- Não implementa remoção forçada, restauração destrutiva nem testes de intrusão em alvos externos.
- Caso falhe após a importação, o VMForge **mantém os arquivos e a VM** para diagnóstico. Não tente rodar `create` novamente com a mesma pasta; avalie o estado antes.
- Não compartilhe arquivos de configuração da VM contendo credenciais, chaves, notas pessoais ou capturas de exercícios ao publicar no GitHub.

## Limitações conhecidas

- Compatibilidade **inicialmente prevista para Windows com VirtualBox e imagens pré-construídas do Kali**. Não há suporte testado para VMware, ISO de instalação, distribuições diferentes, imagens já modificadas ou importação clonada de uma VM registrada.
- A instalação completa *end-to-end* ainda precisa ser executada num computador Windows com VirtualBox; os testes unitários não substituem esse teste.
- `getpass` depende de terminal compatível. Testar com NVDA no PowerShell e Git Bash.
- A atualização de pacotes pode demandar muito tempo/espaço e reinicialização. O snapshot é feito após solicitar o desligamento, mas a atualização do kernel só será ativada no próximo boot.
- Burp Suite/Wireshark são gráficos e exigem planejamento de acessibilidade separadamente.
- Este protótipo não é tolerante a todos os erros de rede nem garante recuperação automática de interrupções.

## Executar testes

```shell
python -m unittest discover -s tests -v
```

## Créditos

Projeto criado para experimentar automação de laboratórios virtuais e acessibilidade por linha de comando. Não possui afiliação com Oracle ou Kali Linux.

Licença: MIT.

## Pastas de laboratorio opcionais

O assistente pergunta se deseja criar `~/pentest-lab/{scans,evidencias,notas}` dentro do Kali. A escolha padrao e **nao**. Recusar nao impede configurar a VM e o SSH. A pasta de destino da imagem da VM continua obrigatoria.

No Windows, caso `vmforge` nao seja encontrado depois de `pip install --user -e .`, adicione a pasta `Scripts` indicada pelo pip ao `PATH`. No Git Bash com Python 3.14: `export PATH="$PATH:/c/Users/julia/AppData/Roaming/Python/Python314/Scripts"` (substitua o usuario e a versao conforme seu ambiente). Alternativamente use `python -m vmforge`.
