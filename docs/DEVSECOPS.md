# Verificacoes de seguranca automatizadas

O VMForge usa os testes automatizados existentes no GitHub Actions e adiciona duas camadas complementares:

- Dependabot: verifica semanalmente atualizacoes do ecossistema Python e das actions do GitHub. Novas versoes podem gerar Pull Requests, que precisam de revisao antes do merge.
- CodeQL: examina codigo Python em Pull Requests, pushes na main, execucoes semanais e acionamento manual. Achados podem aparecer na area Security > Code scanning do GitHub.

O CodeQL e o Dependabot nao substituem testes de integracao com VirtualBox real, revisao humana ou validacao das permissoes e configuracoes do repositorio.

O workflow CodeQL precisa de permissao para gravar eventos de seguranca. Se o repositorio tiver CodeQL Default Setup habilitado, confira a configuracao para evitar analises duplicadas antes de integrar este workflow avancado.

O Dependabot de atualizacoes de versao e configurado por `.github/dependabot.yml`. Os alertas e atualizacoes de seguranca do Dependabot tambem dependem das configuracoes do repositorio.

Os resultados e eventuais falhas dos novos jobs devem ser revisados no Pull Request antes do merge. Nenhum merge automatico e ativado por este script.
