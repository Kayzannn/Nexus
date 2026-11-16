# Evidências de validação

## Ambiente observado

Python 3.12 em Linux, Qt em modo offscreen. Este documento não certifica Windows 10/11, Python 3.14 ou uma máquina sem Python. O workflow de CI define esses alvos, mas não foi executado a partir desta sessão.

## Resultado desta entrega

Comando executado no ambiente virtual com extras `dev`, `experimental` e `build`:

```sh
python -m pytest -q --junitxml=/tmp/nexus-pytest-final.xml
```

**41 testes passaram em 9,30 segundos.** Nenhum teste falhou ou foi ignorado nessa execução. Os testes antigos baseados em unittest são coletados pelo pytest; os testes novos de aceitação usam fixtures pytest. Cinco testes da interface anterior têm marcador `experimental` e podem ser excluídos com `-m 'not experimental'`.

Verificações adicionais executadas:

- `python -m pip check`: nenhuma dependência quebrada.
- `python -m compileall -q nexus main.py build.py tests`: sem erros de compilação.
- `git diff --check`: sem problemas de whitespace.
- `python build.py --dry-run`: comando gerado sem subprocesso de build.
- `python -m nexus --help`: entrada e opções disponíveis.
- A janela padrão foi renderizada em Qt offscreen para inspeção visual; isso não substitui uma sessão desktop nativa.

## Escopo dos testes

| Área | Evidência |
| --- | --- |
| Fundação | Navegação padrão com três páginas, configurações persistentes, temas e isolamento das dependências experimentais |
| Arquivos | Análise recursiva, filtros, EXIF, enumeração por captura, categorias, cópia exclusiva e duplicados |
| Segurança | Cancelar prévia, simulação sem alterações, destinos ocupados, origem alterada, falha individual e parada diante de estado incerto |
| Histórico | Registros por arquivo/lote, erros com traceback, desfazer e referências de catálogo |
| Recuperação | Interrupção após movimentação, desfazer interrompido, estados ambíguos preservados e falha de persistência após mudança física |
| SQLite | Reabertura, migração de dados antigos, rollback de esquema/versão e rejeição de banco mais recente |
| Unicode | Pasta e nomes com espaços, acentos e caracteres japoneses; renomeação/desfazer reais |
| Interface prioritária | Seleção após ordenação, busca, cancelamento, simulação e fluxo confirmado de renomeação/desfazer pela UI |
| Distribuição | Contrato do comando de build, dry-run sem execução, rejeição de compilação cruzada e dados fora de `_MEIPASS` |
| Experimental | Sessões/cadastros existentes, catálogo de imagem, backup, PDF, subprocesso autorizado, saída e interrupção |

## Medição com 3.000 arquivos

O teste cria 3.000 arquivos reais pequenos, com Unicode e espaços, em uma pasta temporária. Abre a página Arquivos, solicita análise assíncrona e carrega o modelo de tabela. Na execução final, a etapa medida de análise + modelo levou **0,322 segundo**, com **8 eventos de timer Qt** durante o trabalho. A duração total desse caso inclui a criação dos arquivos e foi aproximadamente 1 segundo.

O teste verifica contagem integral e processamento de eventos, não apenas um resultado vazio ou uma porta aberta. O modelo usa registros por linha, não milhares de widgets por célula. A medição não é uma promessa de desempenho em discos externos, rede ou arquivos RAW grandes, nem certifica ausência de qualquer pausa em todas as operações futuras.

## Pendências externas

- Executar a matriz de CI em Windows e Python 3.14 e inspecionar seus resultados.
- Testar arquivos bloqueados, junctions, permissões NTFS e movimentação real entre volumes no Windows. A suíte local inclui falhas de permissão e troca de volume simuladas.
- Gerar o executável Windows e abrir em máquina limpa sem Python, conforme `docs/windows.md`.
- Validar visualmente o tema e o redimensionamento em uma sessão Windows nativa.
- Revisar as fases experimentais uma por vez, com arquivos RAW e fluxos reais, antes de promovê-las.

Nenhum executável Windows foi gerado nesta sessão. O build foi validado apenas como comando e contrato de execução.
