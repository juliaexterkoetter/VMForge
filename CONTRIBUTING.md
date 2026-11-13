# Como contribuir para o VMForge Community

Contribuições de código, testes, documentação, correções de segurança e acessibilidade são bem-vindas.

Antes de desenvolver uma alteração grande, abra uma issue para discutir a proposta. Para uma correção pequena, você pode abrir diretamente um Pull Request.

## Ambiente e testes

Utilize Python 3.12 ou 3.14. Execute, na raiz do projeto:

```bash
python -B -m unittest discover -s tests -q
```

Mantenha a compatibilidade com Windows e Ubuntu quando aplicável. Inclua testes para novos comportamentos e correções. Não rode testes em máquinas virtuais ou sistemas sem autorização.

## Segurança e privacidade

Nunca inclua credenciais, tokens, dados pessoais, UUIDs reais de laboratórios, imagens VDI ou arquivos de configuração privados. Verifique o diff antes do envio.

Mudanças que afetem validação de arquivos, execução do VBoxManage ou proteção de VMs devem preservar o comportamento seguro e adicionar testes adequados.

## Acessibilidade

Priorize interfaces operáveis pelo teclado, textos claros para leitores de tela e mensagens que não dependam apenas de cores.

## Licença das contribuições

O projeto usa a Apache License, Version 2.0. Contribuições submetidas intencionalmente para inclusão no projeto são oferecidas nos termos da seção 5 dessa licença, salvo declaração explícita em contrário aceita pela mantenedora.

Contribua apenas com material que você tenha direito de disponibilizar. Os direitos autorais das contribuições não são automaticamente transferidos à mantenedora. O envio de um PR não constitui, por si só, autorização para relicenciar contribuições sob termos diferentes.

## Conduta

Seja respeitoso e mantenha discussões técnicas construtivas. Assédio, discriminação e exposição de dados privados não são aceitos.
