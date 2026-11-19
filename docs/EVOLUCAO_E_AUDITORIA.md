# Evolução e auditoria — 19/11/2026

## Estado inicial e preservação

Versão mantida: **0.2.0rc1**. Raiz original na branch
`feature/import-vmdk-hostonly`, HEAD `dce321a`. Havia alterações não commitadas
em `cli.py`, `recovery.py` e três arquivos de importação. Permanecem intactas.
O trabalho novo está no worktree `.worktrees/consolidacao`, branch
`integration/auditoria-20261119`, baseado em `5f26d11` (topo da cadeia original).
Nenhum merge em main, exclusão de branch/worktree, force-push ou operação em VM real.

Os worktrees de auditoria solicitados foram encontrados. As cinco revisões finais
estavam limpas. A tentativa anterior `161640` tinha três arquivos modificados,
preservados. Os relatórios finais diziam `Testes: None`, embora os logs contivessem
execuções: isso não foi usado como aprovação da integração.

## Recuperação revisada

| Origem | Recuperação | Decisão |
|---|---|---|
| PR 21 / `53715eb` | `3efc07e` | Parser VMDK, cópia privada, hashes, UUIDs e rede desativada antes do registro; preservadas também regras Windows posteriores |
| PR 22 / `51107e5` | `bf83a40` | CLI em português, stderr, cancelamento; descartados testes do fluxo antigo que clonava a origem diretamente |
| PR 23 / `a893ace` | `ef1b384` | Laboratórios multi-VM, diário e rede interna exclusiva |
| PR 24 / `cec157d` | `4578595` | Snapshots, restauração confirmada e diagnóstico; testes separados de lab para evitar colisão |
| PR 25 / `e873b85` | recuperação seletiva posterior | Workflows e runner de mocks; documentação e implementação antiga incompatíveis não copiadas |

Os PRs originais 23 e 24 não continham as funcionalidades prometidas nos títulos.
As auditorias foram feitas independentemente sobre cada branch, não em sequência.
O merge textual introduzia dois parsers `lab`; a integração corrigiu a colisão
e manteve os aliases `lab snapshot`, `lab restore`, `lab diagnose`.

## Arquitetura e funcionalidades

CLI encaminha para módulos de domínio; o provedor encapsula VBoxManage.
`protection` bloqueia mutações sem configuração local válida. `extraction` e
`appliance` validam o arquivo e isolam sua cópia. `wizard`, `recovery` e `resume`
continuam responsáveis pelos fluxos Kali existentes.

Implementações disponíveis nesta branch:

- Importação VMDK com cópia privada, validação de extents, hashes, limite de
  128 GiB/128 extents, cálculo conservador de espaço, verificação de UUID do
  clone e falhas preservando estado. Sem NAT, Bridge, início ou limpeza automática.
- Laboratórios `.7z` em rede **interna**, plan/create/start/status/stop/list/inspect.
  A rede interna não é Host-only; o modelo Kali + Metasploitable solicitado ainda
  não está implementado. Não use este fluxo como substituto desse modelo.
- Cinco templates declarativos: linux-basico, kali-estudos, dois-linux,
  testes-rede e desenvolvimento. São exemplos para appliances compatíveis `.7z`,
  não instaladores de sistemas nem garantia de compatibilidade de qualquer imagem.
- Inventário somente de leitura com UUID, recursos, redes, UUIDs de discos,
  snapshots, proteção e alertas de acesso externo. Texto/JSON/Markdown.
- Snapshots: criação confirmada, lista/current, diagnóstico e restauração
  confirmada por UUID; `restore --dry-run` apenas consulta e apresenta consequências.
- Revalidação do UUID retornado pelo provedor, criação exclusiva do arquivo
  temporário do diário e revalidação após confirmação de descarte de VM de teste.

## Validação e evidências

Executar na raiz desta branch:

```text
python -B scripts/test_mocked.py
python -m pip wheel --no-deps --wheel-dir dist .
```

O runner bloqueia processos externos durante os testes, verifica sintaxe e gera
`work/quality.json` com comando, código de saída, testes, falhas, erros, exclusões,
Python, SO, commit, estado dirty e data UTC. O log completo local é
`work/test-results.log`. Exclusões não equivalem a testes aprovados.

Primeiras etapas: 34 testes VMDK; depois 43 VMDK/CLI; 23 de laboratório e 15 de
snapshots. A contagem final e o commit validado ficam no registro de evidências.
O build isolado de wheel funcionou; a tentativa sem isolamento falhou por ausência
de setuptools no ambiente original. O ambiente limpo de instalação fica em
`work/package-env`. Não foi instalado Python adicional: apenas 3.14.7 disponível.

## CI remota verificada

Consultas via `gh` falharam com HTTP 401. O conector GitHub confirmou os cinco
PRs abertos e em rascunho, com bases encadeadas e os mesmos SHAs locais.
Para `c8b9a21`, os runs 44589306528 (CodeQL) e 44589306571 (testes) tiveram sucesso.
Não foram encontrados runs de pull_request associados aos SHAs de 22–25.
Esses resultados são da cadeia original, **não certificam as alterações novas**.
Os workflows recuperados removem o filtro de base main para testar PRs encadeados.
Matriz Windows/Ubuntu, Python 3.12/3.14, wheel, instalação e smoke tests da CLI.

## Pendências e riscos conhecidos

- VirtualBox real, boot, preservação de discos reais, Windows/Git Bash e NVDA
  precisam de validação humana em VMs descartáveis após autorização explícita.
- Python 3.12 e Linux ainda dependem da nova CI ou ambiente apropriado.
- Não há cobertura percentual medida nem auditoria de dependências conclusiva.
- Não há parser integral das tabelas internas de grains VMDK; a clonagem pode
  recusar imagens estruturalmente inválidas. Hash local não autentica fornecedor.
- Pastas privadas são requisito; revalidações não eliminam todas as condições
  de corrida contra processos concorrentes com acesso de escrita.
- Importação não tem diário persistente por etapa nem comando próprio para
  diagnóstico de interrupção. Mensagens e arquivos parciais são preservados.
- Laboratórios não suportam ainda VMDK, funções de máquinas, IPs observados,
  inventário de serviços, Host-only declarativa ou retomada completa de criação.
- Snapshots não têm política própria por UUID de snapshot, histórico persistente
  ou árvore de dependências; a proteção atual é por VM.
- Inventário não correlaciona laboratórios automaticamente, não verifica DHCP,
  portas SSH nem conectividade. Não há sondas, scanners ou ferramentas ofensivas.
- Assistente numerado existente preservado; novas funções acessíveis por comandos,
  ainda sem todas as opções no menu interativo.

Não declarar a evolução completa ou uma versão estável antes de fechar essas
lacunas, revisar os PRs e executar as validações reais autorizadas.
