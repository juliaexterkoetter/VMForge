# Comandos novos e validação

Execute com o Python do ambiente virtual. Ajuda: `python -m vmforge COMANDO --help`.

```text
python -m vmforge template list
python -m vmforge template show dois-linux
python -m vmforge lab plan manifesto.json
python -m vmforge lab create manifesto.json --directory NOVA_PASTA
python -m vmforge lab list PASTA_DOS_LABS
python -m vmforge lab inspect PASTA_DO_LAB
python -m vmforge lab status PASTA_DO_LAB
python -m vmforge lab start PASTA_DO_LAB
python -m vmforge lab stop PASTA_DO_LAB
python -m vmforge report --format json
python -m vmforge report --format markdown
python -m vmforge snapshots UUID_DA_VM
python -m vmforge restore UUID_DA_VM UUID_DO_SNAPSHOT --dry-run
```

Copie o JSON de `template show` para um arquivo UTF-8 e ajuste os caminhos das
imagens locais. O schema está em [lab-manifest-v1.schema.json](lab-manifest-v1.schema.json).
O planejamento verifica os campos e os arquivos; a preparação faz a validação
completa do appliance. Campos executáveis não são aceitos. Não há downloads.

Laboratórios usam rede interna exclusiva. Para VMDK individual, consulte
[IMPORTACAO_VMDK.md](IMPORTACAO_VMDK.md): Host-only existente é obrigatória.
Não há template operacional Kali + Metasploitable nesta etapa.

`report` retorna 1 se alguma consulta falhar; o JSON preserva resultados parciais.
Somente campos selecionados são exportados. UUIDs de discos são incluídos;
caminhos de discos, propriedades de convidado e credenciais são omitidos.
`lab inspect` lê o diário local; ele pode conter caminhos privados. Revise antes de compartilhar.

Restauração real omite `--dry-run`, mostra o risco de perda do estado atual e
exige digitar o UUID inteiro da VM. Não aceita confirmação automática. A VM
deve estar desligada e desprotegida. Nada apaga snapshots automaticamente.

## Windows e NVDA

Use PowerShell ou Git Bash, teclado e comandos textuais. Não há cores obrigatórias.
Enter vazio cancela confirmações; Ctrl+C interrompe e retorna falha. Após erro em
operação mutável, preserve os arquivos e consulte status/diagnóstico antes de repetir.
Configure UTF-8 quando necessário, como descrito no README. Não há teste humano
com NVDA registrado para estes comandos. Avalie leitura de ajuda, plano,
confirmação, erro, cancelamento e relatório em sessão separada.

## Recuperação

Em falhas de laboratório, preserve `lab.json` e consulte `lab inspect` e `lab status`.
Não repita create no mesmo diretório nem adote uma VM externa. Um `lab.tmp` deixado
por falha interrompe novas gravações; inspecione os dois documentos antes de
qualquer correção manual. Não existe limpeza destrutiva automática.
O descarte restrito `purge-test` revalida identidade, estado e disco depois da
confirmação e recusa appliances com snapshots ou referências externas.
