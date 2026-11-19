# Laboratorios multi-VM

O grupo `vmforge lab` importa de 1 a 32 VMs independentes a partir de appliances
`.7z` contendo um `.vbox` e um VDI independente, com as mesmas restricoes de
seguranca da importacao existente. A configuracao local de protecao continua
obrigatoria para criar e alterar VMs.

Salve este manifesto como `training.json`:

```json
{
  "version": 1,
  "name": "training",
  "vms": [
    {"name": "attacker", "image": "kali.7z", "ram": 4096, "cpus": 2},
    {"name": "target", "image": "target.7z", "ram": 2048, "cpus": 1}
  ]
}
```

O [esquema v1](lab-manifest-v1.schema.json) documenta os campos. O programa
valida tambem existencia das imagens e unicidade dos nomes sem distinguir
maiusculas. Caminhos relativos de imagem partem da pasta do manifesto.
Campos desconhecidos, chaves duplicadas e versoes desconhecidas sao recusados.
RAM e CPUs omitidos usam 4096 MB e 2 CPUs.

```text
vmforge lab plan training.json
vmforge lab create training.json --directory ./training-lab
vmforge lab status ./training-lab
vmforge lab start ./training-lab
vmforge lab stop ./training-lab
```

`plan` valida a estrutura e a existencia das imagens sem acessar o VirtualBox,
extrair arquivos ou gravar estado. Nao verifica o conteudo dos arquivos, espaco
livre ou conflitos com VMs registradas; essas verificacoes ocorrem na criacao.
`create` exige destino inexistente e cria VMs desligadas, chamadas
`training-attacker` e `training-target`. `create`, `start` e `stop` mostram a
operacao e exigem digitar `SIM`; `--yes` e a confirmacao explicita para automacao.

Cada laboratorio recebe uma rede interna `vmforge-<UUID-do-laboratorio>`.
Apenas o primeiro adaptador fica ativo; NAT, bridge e os demais adaptadores sao
removidos da copia antes do registro. Os convidados nao recebem IPs do VMForge:
configure IPs estaticos na mesma sub-rede dentro deles. Nao ha DHCP, internet,
encaminhamento de portas, SSH ou provisionamento automatico neste fluxo.
Uma rede interna separa o trafego do host; um administrador do VirtualBox ainda
pode conectar manualmente outra VM a ela. `start` verifica a rede antes de iniciar.

`lab.json` no destino registra versao, nome, UUID do laboratorio, rede, UUIDs das
VMs e discos, caminhos das configuracoes, etapas e erros. O UUID e persistido
antes da tentativa de registro para cobrir timeout apos sucesso externo.
Atualizacoes sao atomicas; `.lab.lock` impede operacoes mutaveis concorrentes
pelo VMForge. Um encerramento abrupto pode deixar o lock; remova-o manualmente
somente depois de verificar que nao existe operacao em andamento.

Falhas retornam codigo 1. Uma criacao parcial preserva o registro, as copias
preparadas e VMs ja registradas; VMs ainda nao processadas ficam no registro
sem UUID. Nao ha rollback destrutivo nem retomada automatica de criacao.
`start` bloqueia VMs incompletas e interrompe o lote na primeira falha; VMs ja
iniciadas permanecem ligadas. `stop` tenta as demais VMs mesmo se uma falhar e
solicita apenas ACPI: sucesso significa pedido enviado, nao desligamento
concluido. Use `status` para consultar novamente. VMs ja desligadas sao ignoradas.
`status` nao altera o registro e mostra estados, etapas e erros; retorna 1 para
VMs ausentes ou criacao incompleta. Nomes, UUIDs e caminhos sao conferidos antes
de operar; as mutacoes usam UUID, nunca resolucao apenas por nome.

A implementacao e testada com fakes e mocks. Validacao real ponta a ponta no
VirtualBox permanece pendente.
