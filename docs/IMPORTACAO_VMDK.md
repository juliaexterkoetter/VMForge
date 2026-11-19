# Importação conservadora de VMDK

Disponível por `python -m vmforge.import_disk` ou `vmforge import-disk`.
Sem `--execute`, apenas valida e apresenta o plano. A execução exige também
`CRIAR`. A proteção local descrita em `PROTECAO_LOCAL.md` é obrigatória;
ausência ou erro bloqueia a operação.

```powershell
python -B -m vmforge.import_disk --source 'C:\Imagens\lab.vmdk' --name Lab-Novo --basefolder 'C:\VMs' --hostonly 'VirtualBox Host-Only Ethernet Adapter'
```

## Formatos e confiança

Use somente imagens de procedência conhecida, com integridade conferida contra
uma referência confiável do fornecedor, incluindo todos os extents. A validação
local não autentica o fornecedor nem determina se o sistema convidado é seguro.

Aceita descritores ASCII versão 1 de `monolithicFlat`, `monolithicSparse`
(descritor embutido), `twoGbMaxExtentFlat` e `twoGbMaxExtentSparse`. Os extents
devem ser arquivos regulares na mesma pasta, com nomes compostos por letras
ASCII, números, ponto, hífen e sublinhado. Valida campos obrigatórios,
assinatura/capacidade sparse, limites do descritor embutido e tamanho flat.
Não valida integralmente tabelas de grains ou o sistema de arquivos convidado;
erros internos podem aparecer na clonagem.

Recusa pais/snapshots/encadeamentos, referências externas ou circulares,
extents ausentes/repetidos, dispositivos raw, links simbólicos, junctions,
hard links e formatos não suportados, inclusive `streamOptimized`.
Não há achatamento automático de cadeias nem conversão de formatos recusados.

## Origem, identidade e rede

O plano registra SHA-256 do descritor e de cada extent. A execução revalida o
plano, copia os arquivos para `source-copy` no novo destino e confere os hashes.
Somente essa cópia privada é entregue ao `clonemedium`; o backend nunca recebe
o caminho original como entrada de clonagem. Os hashes originais são conferidos
após o clone e na saída, inclusive em falhas. Isso detecta alterações externas,
mas não bloqueia outros processos nem garante proteção contra um adversário
que altera arquivos concorrentemente. Mantenha a origem estável.

O destino e o nome não podem existir. A nova VM recebe UUID explícito; colisões
e proteção por UUID/nome são verificadas. Alterações posteriores usam esse UUID
e revalidam identidade, proteção e estado desligado.

`createvm` cria uma configuração **não registrada**. Antes do registro, todos
os oito adaptadores são explicitamente desativados no XML. A clonagem usa VDI
Standard; antes do registro, o cabeçalho VDI deve indicar imagem normal/fixa,
UUID não nulo e ausência de UUIDs de pai/vínculo. Não se anexa o VMDK original.

Depois do registro, somente NIC 1 Host-only é configurada, NICs 2–8 ficam
desativadas. O estado de rede retornado é conferido antes de anexar o disco.
Não se configura NAT ou Bridge e não se inicia a VM. A Host-only precisa existir;
não há criação de interfaces ou gestão de DHCP.

## Falhas e espaço

Qualquer falha interrompe a sequência, informa a etapa e preserva o estado
parcial para inspeção, inclusive falhas/timeouts de `createvm`. Não há exclusão,
desregistro, nova tentativa ou início automático. Uma falha de criação/clone
ocorre antes do registro; falhas posteriores partem da rede desativada ou
Host-only. Não repita sem inspecionar o destino e o registro.

A pasta `source-copy` é preservada também no sucesso; reserve espaço para ela
e para o VDI. O plano verifica espaço para a cópia, capacidade lógica do clone
e margem de 512 MiB; a execução revalida. Não há pré-reserva de espaço nem
limpeza automática. Limites: 128 extents e capacidade total de 128 GiB.

## Testes

```powershell
python -B -m unittest discover -s tests -p test_import_disk.py -v
```

Os testes de importação usam mocks/fakes, injetam falhas em criação, clonagem,
registro, configuração e conexão do disco, verificam proteção e isolamento e
comparam hashes de todos os arquivos originais. O fake também modifica a cópia
privada para demonstrar que essa escrita não alcança a origem.

Não houve validação com VirtualBox/VMs reais nesta revisão. A suíte existente
contém testes de integração com extratores e subprocessos reais; esses testes
devem ser excluídos quando a execução estiver restrita a mocks/fakes.
