# Entrega por fases

A ordem vigente prioriza concluir e validar Fundação e Arquivos antes de promover os demais módulos. Código exploratório anterior foi preservado, mas não é carregado na execução padrão.

| Fase | Situação nesta entrega | Próximo marco |
| --- | --- | --- |
| 1 — Fundação | Implementada; validação local com pytest e Qt headless | Validar aparência e comportamento nativos no Windows |
| 2 — Arquivos | Implementada; análise, filtros, tabela virtual, EXIF, enumeração, prévia, simulação, cópia, categorias, duplicados, histórico, desfazer e recuperação testados | Testar bloqueios NTFS, discos externos, permissões e cargas reais de fotografias no Windows |
| 3 — Dashboard e estudos | Estruturas SQLite e implementações experimentais de disciplinas, atividades, calendário, sessões e Pomodoro | Revisar UX/CRUD e vínculos entre cadastros; testes completos de calendário, cronômetro e produtividade antes da promoção |
| 4 — Impressão 3D e fotografia | Estruturas e implementações experimentais de perfis, CSV/PDF, EXIF, miniaturas, álbuns e backup | Validar RAW de câmeras reais, imagens anexadas, relatórios nativos e consistência do catálogo com operações externas |
| 5 — Automação | Cadastro explícito de scripts, QProcess, saída, progresso e interrupção em implementação experimental | Revisar UX de autorização e validar processos no Windows; testar saída volumosa, argumentos e falhas em cenários reais |
| 6 — Distribuição | Script de build e documentação preparados; nenhum binário Windows validado aqui | Gerar e testar pacote em Windows 10/11 sem Python; definir instalador, assinatura e lockfile de distribuição |

## Critério de promoção

Um módulo só deve entrar na janela padrão após testes dos serviços, integração da interface e demonstração real das suas operações. Uma tela ou callback sem operação real não conta como recurso concluído. Indicadores devem usar dados persistidos; estados vazios devem aparecer como ausência de dados, sem valores fictícios.

Não há necessidade de reescrever código já funcional das fases posteriores. A próxima etapa é revisar, corrigir e validar um módulo por vez. `--experimental-modules` é uma opção explícita de desenvolvimento, não uma declaração de prontidão desses módulos.
