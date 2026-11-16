# NEXUS — Personal Automation Hub

Aplicativo desktop local para Windows 10/11. Esta entrega prioriza **Fase 1 — Fundação** e **Fase 2 — Gerenciamento de arquivos**, com Python 3.12+, PySide6, SQLite, Pillow e ExifRead.

A execução padrão oferece Início, Arquivos e Configurações. Implementações anteriores das Fases 3–5 foram preservadas como **experimentais**, sem serem apresentadas como módulos concluídos da distribuição padrão. Não há números fictícios, serviços externos obrigatórios ou download/execução automática de scripts.

## Executar no Windows

No diretório do projeto, em PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,build]"
.\.venv\Scripts\python main.py
```

Também funciona `python -m nexus` ou o comando `nexus` do ambiente virtual. Para instalar apenas as dependências de execução, use `python -m pip install -r requirements.txt`; as versões são declaradas uma única vez em `pyproject.toml`.

No Linux, para desenvolvimento:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,build]'
.venv/bin/python -m nexus
```

Qt precisa das bibliotecas gráficas da distribuição. Testes headless são configurados automaticamente em Linux sem tela. A validação desta entrega foi feita com **Python 3.12 no Linux**. Python 3.14 e Windows 10/11 são alvos de compatibilidade, com matriz de CI preparada, mas seus resultados não foram verificados nesta máquina.

## Fase 1: fundação implementada

- Janela principal com barra lateral e páginas roláveis, tema escuro inicial, opção clara persistida e páginas opacas para evitar sobreposição de conteúdo.
- Inicialização automática do SQLite e migrações transacionais até a versão 3, preservando dados existentes e rejeitando bancos de versões futuras.
- Configurações no SQLite, logs locais rotativos e tabela de erros com contexto e traceback.
- Workers sem acesso a widgets; sinais enfileirados atualizam a interface na thread principal.
- Caminhos de dados independentes da instalação e da extração temporária do executável.

## Fase 2: gerenciador implementado

1. Selecione a pasta e marque **Incluir subpastas** quando necessário. A análise não renomeia, copia ou move arquivos. Links simbólicos e junctions não são percorridos.
2. Veja nome, extensão, tamanho em bytes, criação, modificação e captura EXIF. Data de criação indisponível aparece vazia; ctime Linux não é apresentado como criação.
3. Filtre extensões como `.jpg,.cr2`, tamanho em KB, período de modificação e pesquisa textual. Clique no cabeçalho para ordenar; números e datas usam seus valores reais.
4. Defina base do nome, prefixo, sufixo e ordenação crescente/decrescente. EXIF ausente usa criação ou modificação, conforme a opção. A enumeração preserva a extensão: `Foto_001.CR2`.
5. Deixe **Simulação (dry-run)** marcada para validar e consultar os caminhos sem executar. A simulação não cria destinos nem histórico de execução.
6. Para executar de fato, desmarque a simulação, solicite a prévia, confira todos os caminhos na tabela e confirme. Cancelar preserva os originais.
7. Organize por categoria, copie a pasta imediata ou identifique duplicados exatos por SHA-256. Destinos existentes nunca são sobrescritos e duplicados nunca são apagados automaticamente.
8. Consulte histórico e erros. **Desfazer** restaura uma renomeação/movimentação quando o conteúdo continua íntegro e a origem está livre. **Conciliar operações interrompidas** verifica caminhos e hashes e ajusta apenas o histórico quando seguro.

Renomear e organizar usam **todos os arquivos visíveis** após filtros e pesquisa, não apenas a linha selecionada. A cópia simples usa a pasta imediata e seu filtro de extensão próprio. A tabela virtual não cria um widget por célula; leitura de disco, hashes, filtragem inicial e consultas do histórico ocorrem em workers.

Falhas independentes são registradas por arquivo e não impedem os demais. Uma alteração física seguida de falha de persistência interrompe o lote para recuperação. Lotes não são uma transação atômica entre SQLite e sistema de arquivos. Trocas cíclicas de nomes e destinos ocupados precisam ser resolvidos antes da execução. Movimentações entre volumes usam cópia exclusiva, verificação de hashes e remoção da origem como parte da operação confirmada.

## Dados e privacidade

- Windows: `%LOCALAPPDATA%\Nexus\nexus.sqlite3`.
- Linux: `~/.local/share/Nexus/nexus.sqlite3`.
- Logs: `logs/nexus.log` junto ao banco, com rotação de 2 MB e três backups.
- Preferências: tabela `user_settings`; não ficam no diretório `_MEIPASS` do PyInstaller.

O SQLite também mantém as tabelas dos módulos futuros e os dados já cadastrados nas versões anteriores. Feche o NEXUS antes de copiar sua pasta de dados para backup. Fotos, materiais e anexos referenciados precisam de backup separado. Banco e logs não são criptografados; logs podem conter caminhos pessoais. Nenhum recurso requer privilégios administrativos.

## Testes com pytest

```powershell
.\.venv\Scripts\python -m pytest -m "not experimental" -q
```

Com dependências opcionais instaladas, execute também os testes dos módulos experimentais:

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev,experimental]"
.\.venv\Scripts\python -m pytest -q
```

No Linux, substitua o caminho pelo `.venv/bin/python`. Os testes cobrem persistência, rollback de migrações, conflitos, EXIF, renomeação, desfazer, recuperação, simulação, falhas individuais, Unicode, espaços, ordenação numérica, cancelamento de prévia, tabela com 3.000 arquivos e retorno dos workers à thread principal. Consulte [evidências de validação](docs/validation.md).

## Executável Windows

Gere **em Windows**, a partir do checkout:

```powershell
.\.venv\Scripts\python -m pip install -e ".[build]"
.\.venv\Scripts\python build.py
```

O resultado esperado é `dist\NEXUS\NEXUS.exe`. Distribua **a pasta inteira** `dist\NEXUS`; Python e bibliotecas necessários são empacotados pelo PyInstaller. Isso precisa ser confirmado em uma máquina limpa sem Python antes de uma distribuição final. O executável Windows não foi gerado nem validado neste ambiente Linux.

`python build.py --dry-run` mostra o comando sem executá-lo. A versão padrão exclui interfaces experimentais, RAW/LibRaw e gráficos. Não há compilação cruzada Windows a partir do Linux. Consulte o [roteiro de distribuição](docs/windows.md).

## Fases seguintes

Estudos/dashboard, impressão 3D, catálogo fotográfico e scripts têm estruturas e implementações exploratórias já existentes. Para inspecioná-las explicitamente:

```powershell
.\.venv\Scripts\python -m pip install -e ".[experimental]"
.\.venv\Scripts\python -m nexus --experimental-modules
```

A janela é identificada como experimental. O extra acrescenta rawpy e PyQtGraph; não é necessário para as Fases 1/2. Um pacote experimental exige `python build.py --experimental` e execução com `NEXUS.exe --experimental-modules`. Não execute scripts que você não tenha revisado e autorizado.

O [plano por fases](docs/roadmap.md) distingue o que já existe do que falta validar ou completar. A arquitetura está em [docs/architecture.md](docs/architecture.md), e os contratos operacionais em [docs/safety.md](docs/safety.md).
