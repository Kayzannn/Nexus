# Contratos de segurança e recuperação

- Análise, EXIF, hashes e planejamento abrem originais para leitura. Links simbólicos/junctions não são percorridos. Diretórios inacessíveis podem ser reportados individualmente sem impedir a análise dos demais. O sistema operacional pode atualizar metadados de acesso por uma leitura normal.
- Simulação começa habilitada na primeira execução e pode ser alterada no gerenciador. A preferência vale para lotes de renomeação/movimentação e cópias, inclusive backups e regras. Não é uma sandbox para scripts Python.
- O dry-run valida os planos e hashes e devolve caminhos e falhas, sem criar destinos, executar alterações ou inserir histórico de execução. A interface pode persistir a preferência do usuário no banco. O teste de simulação confirma que os arquivos e o histórico permanecem intactos.
- Para executar de fato, desmarque a simulação, leia a prévia e confirme. Fechar a prévia ou escolher Não cancela a alteração. Não existe comando de exclusão permanente de arquivos na interface; excluir um cadastro remove somente o registro, após confirmação.
- Movimentação entre discos copia exclusivamente, confere hashes e remove a origem como parte da movimentação explicitamente confirmada. Uma cópia parcial criada pela própria operação pode ser removida na limpeza de falha; nunca se remove um destino preexistente.
- Nomes inválidos e destinos existentes são rejeitados. Lotes com origens repetidas, destinos repetidos ou dependências entre origens/destinos são bloqueados. Nenhuma opção habilita sobrescrita.
- A interface continua após falhas independentes de arquivo e informa quantidades e detalhes. Se uma alteração física ocorre e a persistência seguinte falha, o lote é interrompido: continuar nesse estado não seria seguro. APIs mantêm `continue_on_error=False` como padrão de compatibilidade e permitem optar pela continuação.
- Cada execução registra o lote antes das alterações e cada arquivo como `pending` antes de atuar. Estados incluem `done`, `failed`, `needs_recovery`, `undo_pending` e `undone`. Sucessos anteriores a uma falha são preservados. Não há promessa de transação atômica entre SQLite e sistema de arquivos.
- Desfazer exige confirmação, destino atual com hash esperado e caminho original livre. Registra `undo_pending` antes da alteração. Cópias não são desfeitas por exclusão automática.

## Conciliar interrupções

Use **Conciliar operações interrompidas** após uma queda ou erro de persistência. A confirmação autoriza inspeção de hashes e atualização do histórico; não move, sobrescreve nem apaga arquivos.

| Evidência | Resultado |
| --- | --- |
| Renomeação/movimentação: origem ausente, destino com hash esperado | Marca concluída e realinha referências do catálogo |
| Origem com hash esperado e destino ausente | Marca falha sem alteração física |
| Cópia: destino com hash esperado | Marca concluída |
| Desfazer pendente: origem restaurada com hash esperado, destino ausente | Marca desfeita |
| Desfazer pendente: destino íntegro e origem ausente | Mantém operação concluída, permitindo tentar desfazer novamente |
| Dois caminhos presentes, conteúdo inesperado ou permissão insuficiente | Reporta ambiguidade e preserva os arquivos para revisão manual |

Lotes conciliados recebem `recovered`; se ainda houver estados pendentes, recebem `needs_recovery`. Uma colisão de referências no catálogo impede realinhamento automático. A recuperação não reconstrói arquivos apagados fora do NEXUS nem substitui backup. Não se deve executar duas instâncias manipulando os mesmos caminhos simultaneamente.

## Scripts e armazenamento local

Scripts só são cadastrados por escolha explícita e autorização, e cada execução pede confirmação. Não há download/execução automática, shell, elevação administrativa nem serviço externo obrigatório. Um script autorizado pode executar qualquer ação permitida pela conta, independentemente da simulação de arquivos. O botão de interrupção controla o processo Python direto, não uma árvore arbitrária de filhos.

A aplicação não solicita privilégios administrativos. O banco, miniaturas e logs ficam na área de dados local do usuário; instalação de dependências é uma etapa explícita de desenvolvimento. Backup da pasta de dados deve ser feito com o aplicativo fechado. Fotos, materiais e imagens anexadas continuam como referências a arquivos externos, que exigem cópia separada.
