# Proteção local de máquinas virtuais

O VMForge utiliza uma configuração local para identificar máquinas virtuais protegidas e portas reservadas.

As informações pessoais de cada laboratório não fazem parte do código-fonte público.

## Localização

Windows:

C:\Users\SEU_USUARIO\.vmforge\config.json

Linux:

~/.vmforge/config.json

Também é possível definir o caminho por meio da variável de ambiente VMFORGE_PROTECTION_CONFIG.

## Exemplo de configuração

~~~json
{
  "protected_vms": [
    {
      "name": "Laboratorio-Principal",
      "uuid": "11111111-2222-4333-8444-555555555555"
    }
  ],
  "reserved_ports": [2222]
}
~~~

Os identificadores apresentados são fictícios.

## Regras de proteção

O VMForge deve impedir alterações em máquinas protegidas, inclusive quando a máquina tiver sido renomeada.

A identificação pelo UUID protege contra alterações baseadas apenas no nome da máquina.

As portas reservadas não devem ser atribuídas a novas máquinas virtuais.

Se o arquivo de configuração estiver ausente ou inválido, as operações que dependem da proteção serão bloqueadas.

## Cuidados

Não publique o arquivo pessoal config.json.

Não execute comandos diretamente no VBoxManage presumindo que as proteções do VMForge serão aplicadas.

Não utilize arquivos ou diretórios de máquinas existentes como destino de uma nova instalação.

Essa proteção é uma camada preventiva do VMForge, não uma restrição de acesso imposta pelo VirtualBox.
