# Execução e distribuição Windows

## Desenvolvimento

1. Instale Python 3.12 de uma fonte oficial e abra PowerShell no checkout.
2. Crie `.venv` com `py -3.12 -m venv .venv`.
3. Execute `.\.venv\Scripts\python -m pip install -e ".[dev,build]"`.
4. Execute `.\.venv\Scripts\python -m pytest -m "not experimental"`.
5. Abra `.\.venv\Scripts\python main.py`.

A ativação do virtualenv no PowerShell é opcional; os comandos com caminho direto não exigem alterar a política de execução de scripts nem obter privilégios administrativos.

## Build

Execute `.\.venv\Scripts\python build.py`. O comando usa PyInstaller, `--windowed` e `--onedir`. A pasta `dist\NEXUS` contém o executável, o runtime Python e bibliotecas Qt. O diretório de trabalho é resolvido a partir de `build.py`, e não de um caminho absoluto do desenvolvedor.

O build padrão não inclui os módulos experimentais. `build.py --experimental` exige instalar `.[experimental,build]`. Use `build.py --dry-run` para conferir os argumentos sem executar.

## Aceitação em máquina limpa

Esta lista é trabalho de validação pendente, não um resultado já obtido:

- Copiar a pasta completa `dist\NEXUS` para Windows 10 e Windows 11 sem instalação de Python e abrir `NEXUS.exe` como usuário comum.
- Abrir a partir de uma pasta com Unicode e espaços; alternar temas e redimensionar a janela.
- Analisar uma pasta de teste com milhares de arquivos; pesquisar e ordenar numericamente e por data.
- Conferir EXIF em JPG/RAW compatíveis, fallback para datas do sistema e preservação das extensões.
- Simular e cancelar operações; confirmar que originais e destinos ficam intactos.
- Renomear/mover um lote de cópias descartáveis e desfazer pelo histórico.
- Testar destino ocupado, arquivo bloqueado, pasta sem permissão, disco externo e interrupção durante uma operação; revisar o histórico e conciliar estados recuperáveis.
- Reiniciar e verificar configurações, histórico e logs em `%LOCALAPPDATA%\Nexus`, fora da pasta do executável e de qualquer extração temporária.

Não há pedido de administrador, instalador ou assinatura de código nesta entrega. O SmartScreen pode avaliar um binário sem assinatura; assinatura e instalador devem ser definidos na Fase 6. Não desabilite mecanismos de segurança para contornar falhas de distribuição. Um erro de biblioteca deve ser corrigido no empacotamento.

## CI

`.github/workflows/tests.yml` define testes de Fundação/Arquivos em Windows e Linux, Python 3.12 e 3.14. A criação desse workflow não significa que ele já executou ou passou. Os resultados nativos precisam ser observados após sua execução no GitHub.
