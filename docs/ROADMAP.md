# Roadmap VMForge

## v0.1.0 — primeiro protótipo

- [x] CLI textual (`check`, `list`, `status`, `start`, `stop`, `snapshot`, `create`).
- [x] Configuração de VirtualBox pela CLI.
- [x] Extração de arquivo `.7z` e importação de `.vbox` em pasta nova.
- [x] NAT local e provisionamento SSH inicial para imagem oficial Kali.
- [x] Troca de senha sobre SSH com verificação da chave de host.
- [x] Snapshot com a VM desligada.
- [x] Testes unitários básicos.
- [ ] Teste completo em uma VM Kali 2026.3 **nova** no Windows 11 + VirtualBox 7.2.
- [ ] Auditoria de segurança e acessibilidade.

## Próximas versões

- [ ] Registro de progresso e retomada após falhas sem duplicar VMs.
- [ ] Política de rollback e exclusão segura, sempre com confirmação.
- [ ] Validação de integridade SHA256 do arquivo original por checksum oficial.
- [ ] Testes ponta a ponta em ambiente descartável.
- [ ] Suporte a clonagem da VM com novo UUID de disco/maquina.
- [ ] Presets de laboratórios e verificação das ferramentas específicas.
- [ ] Internacionalização, validação com NVDA e Orca.
- [ ] Suporte Linux/macOS; novos sistemas convidados/hipervisores.
