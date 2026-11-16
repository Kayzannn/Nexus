# Arquitetura e persistência

## Organização

```text
main.py                    # entrada direta
requirements.txt           # instala as dependências declaradas em pyproject.toml
build.py                   # PyInstaller em Windows, simulação em qualquer plataforma
nexus/
  core/
    database.py            # conexões SQLite curtas, commit/rollback e fechamento
    migrations.py          # migrações ordenadas por PRAGMA user_version
    settings.py            # configurações JSON no SQLite
    logger.py              # logs rotativos e tabela de erros
    workers.py             # QRunnable e sinais sem acesso a widgets
  ui/
    foundation.py          # janela padrão das Fases 1/2
    models.py              # QAbstractTableModel e proxy com texto de pesquisa em cache
    dialogs.py             # prévia virtualizada e resultados
    main_window.py         # integração experimental das Fases 3–5
    sidebar.py             # navegação
    dashboard.py           # consultas e indicadores reais
    themes.py              # paletas e estilos
    base.py                # componentes e formulários compartilhados
  modules/
    file_manager/          # serviços tipados e mixin da interface prioritária
    study_manager/         # validação de atividades acadêmicas
    printing_3d/           # validação de perfis e CSV
    photography/           # EXIF, RAW, miniaturas e coleções
    script_manager/        # validação de scripts locais e argumentos
  services/
    workspace.py           # repositório compartilhado de cadastros estruturados
    records.py             # sessões e calibrações simples da versão inicial
    automations.py         # regras de cópia
  resources/icons/         # local reservado para ativos futuros
 tests/                     # testes com arquivos e bancos temporários
 docs/                      # contratos de arquitetura e segurança
```

`nexus/app.py`, `nexus/db.py`, alguns módulos em `services/` e `ui/theme.py` mantêm importações compatíveis com versões anteriores. As implementações de arquivos e fotografia ficam em `modules/`; não há duas implementações paralelas. A janela padrão combina `foundation.py` com `modules/file_manager/ui.py`; os formulários antigos em `main_window.py` são exclusivos da opção experimental. Regras e persistência permanecem fora dos widgets. Não foi criado um framework de plugins que executa código externo automaticamente.

## Tabelas

| Domínio | Tabelas |
| --- | --- |
| Configurações | `user_settings` (JSON, chave única, data de atualização) |
| Disciplinas e materiais | `subjects`, `materials` |
| Tarefas, provas e compromissos | `activities` (tipo, prazo e conclusão) |
| Sessões de estudo | `studies` |
| Impressoras e filamentos | `printers`, `filaments` |
| Perfis e calibrações | `profiles`, `calibrations` |
| Fotografia | `photos`, `photo_details`, `albums`, `album_photos` |
| Scripts e execuções | `scripts`, `script_runs` |
| Regras de cópia | `automations`, `runs` |
| Histórico de arquivos e lotes | `file_operations`, `operation_batches` |
| Erros | `error_logs` (contexto, mensagem, traceback e data) |

Registros legados usam nomes textuais de disciplinas/impressoras/filamentos, preservados na migração; não são apresentados como chaves estrangeiras normalizadas. A relação lote/operações usa chave estrangeira, ativada nas conexões. Queries dinâmicas de tabelas usam listas permitidas; valores são parametrizados.

## Migrações

Inicialização automática pelo construtor de `Database`. Versão atual: **3**.

1. Base inicial: sessões, calibrações, fotografias, regras e execuções.
2. Cadastros estruturados, álbuns, scripts e operações de arquivos.
3. Configurações, erros, lotes, vínculo de operações e índices.

Cada atualização ocorre sob `BEGIN IMMEDIATE`; DDL e `user_version` são confirmados juntos. Uma falha reverte a atualização inteira. Não se usa `executescript` para aplicar migrações, pois seu comportamento de commit implícito comprometeria esse contrato. Bancos com versão mais nova são rejeitados antes de alterar o esquema. A migração 2 também garante tabelas iniciais com `IF NOT EXISTS`, para preservar compatibilidade com instalações iniciais parciais.

Para uma futura versão, acrescente uma entrada em `MIGRATIONS`, incremente `SCHEMA_VERSION` e teste migração de um banco antigo com dados, repetição da inicialização e rollback diante de falha. Não edite migrações já publicadas. Faça backup com o aplicativo fechado antes de atualizar uma instalação importante.

## Configurações e logs

Tema, preferência de simulação e interpretador Python são persistidos no SQLite. A janela padrão lê diretamente o SQLite. A janela experimental mantém a importação de tema legado de QSettings apenas quando a preferência ainda não existe.

Logs em `logs/nexus.log`, junto ao banco: rotação de 2 MB, até três backups. Operações registram início/fim de lote e caminhos; exceções incluem contexto e traceback. Erros também aparecem em `error_logs`, consultável na interface. Falha de escrita SQLite tenta preservar o erro no log rotativo. Não há envio externo, dump de variáveis de ambiente ou cópia da saída completa de scripts nesses logs; a saída autorizada de scripts fica em `script_runs`.

O histórico SQLite não é podado automaticamente. Logs podem conter nomes de arquivos e mensagens pessoais; proteja os arquivos de dados e faça retenção conforme sua necessidade.


## Volume de arquivos e responsividade

A distribuição padrão usa `RecordModel`/`RecordProxy`/`RecordView`, baseados em QAbstractTableModel e QTableView. Não cria QTableWidgetItem por célula. O modelo mantém os registros originais e os papéis de ordenação numérica/data; pesquisar ou ordenar não altera a identidade do arquivo selecionado. O proxy consulta um texto casefold preparado por linha em worker, com debounce de pesquisa.

A análise e os filtros de atributos ocorrem em workers. Resultados de análises/filtros antigos têm identificadores de geração e são ignorados quando uma solicitação mais nova os substitui. O histórico também é consultado e preparado fora da thread gráfica. As mudanças de modelo e widgets são feitas na thread principal por sinais enfileirados. O pool da janela padrão tem um worker para serializar operações de disco nessa janela; isso não é um bloqueio entre processos independentes.

Hashes são calculados em blocos de 1 MB. A busca de duplicados primeiro agrupa pelo tamanho atual e só calcula hash dos grupos com mais de um candidato. Arquivos que não têm formato de imagem reconhecido não passam pela tentativa de leitura EXIF. Caminhos usam pathlib e strings Unicode, sem shell.

Testes de aceitação usam um loop Qt real e um timer durante a análise de 3.000 arquivos. O tempo observado é uma medição local, não garantia para discos de rede, arquivos RAW grandes ou outras máquinas. As dependências de RAW/revelação e gráficos são extras opcionais das fases posteriores.
