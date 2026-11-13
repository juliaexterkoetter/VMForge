# Recuperacao e limpeza controlada

`vmforge recover` aceita uma imagem previamente extraida e exige UUIDs esperados
para a VM e para o disco. A recuperacao nao extrai novamente e nao altera a
imagem 7z original. Confirma as identidades, os caminhos, os conflitos de nome,
porta e disco antes do registro. O comando nao pode ser repetido apos registro.

`vmforge purge-test` exclui somente uma VM registrada, desligada e nao protegida,
exigindo correspondencia entre UUID e caminho .vbox registrado e digitacao da
frase `EXCLUIR <UUID>`. Usa `VBoxManage unregistervm <UUID> --delete`.
Arquivos remanescentes exigem revisao manual. Nunca execute sobre imagens
originais ou VMs protegidas. Os comandos devem rodar no Python do Windows,
mesmo quando iniciados pelo WSL.
