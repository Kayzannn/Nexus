"""Dashboard consultando exclusivamente os dados persistidos."""
from datetime import datetime
from PySide6.QtWidgets import QLabel, QHBoxLayout, QPlainTextEdit


class DashboardMixin:
    def build_dashboard(self):
        layout = self.page('Início')
        self.greeting = QLabel()
        self.greeting.setStyleSheet('font-size: 23px; font-weight: 600; padding: 12px;')
        layout.addWidget(self.greeting)
        cards = QHBoxLayout()
        self.cards = {}
        for key, title in [('pending', 'Atividades pendentes'), ('minutes', 'Minutos estudados'), ('files', 'Arquivos processados'), ('photos', 'Fotos catalogadas')]:
            label = QLabel(title+'\n0')
            label.setObjectName('card')
            label.setWordWrap(True)
            cards.addWidget(label)
            self.cards[key] = (label, title)
        layout.addLayout(cards)
        self.dashboard_text = QPlainTextEdit()
        self.dashboard_text.setReadOnly(True)
        layout.addWidget(self.dashboard_text)
        shortcuts = QHBoxLayout()
        for title, index in [('Analisar arquivos', 1), ('Planejar estudos', 2), ('Calibrar impressão', 3), ('Importar fotos', 4), ('Executar script', 6)]:
            self.button(shortcuts, title, lambda i=index: self.navigation.setCurrentRow(i))
        layout.addLayout(shortcuts)
        self.button(layout, 'Atualizar indicadores', self.refresh)

    def refresh_dashboard(self):
        if not hasattr(self, 'cards'):
            return
        now = datetime.now()
        self.greeting.setText(f"Olá!  {now:%d/%m/%Y} — {now:%H:%M}")
        values = {
            'pending': self.db.rows('SELECT COUNT(*) AS n FROM activities WHERE done=0')[0]['n'],
            'minutes': self.db.rows('SELECT COALESCE(SUM(minutes),0) AS n FROM studies')[0]['n'],
            'files': self.db.rows("SELECT COUNT(*) AS n FROM file_operations WHERE status='done'")[0]['n'],
            'photos': self.db.rows('SELECT COUNT(*) AS n FROM photos')[0]['n'],
        }
        for key, (label, title) in self.cards.items():
            label.setText(f'{title}\n{values[key]}')
        due = self.db.rows('SELECT * FROM activities WHERE done=0 ORDER BY due LIMIT 8')
        files = self.db.rows('SELECT * FROM file_operations ORDER BY id DESC LIMIT 6')
        profiles = self.db.rows('SELECT * FROM profiles ORDER BY id DESC LIMIT 4')
        legacy = self.db.rows('SELECT * FROM calibrations ORDER BY id DESC LIMIT 4')
        runs = self.db.rows('SELECT * FROM script_runs ORDER BY id DESC LIMIT 4')
        lines = ['PRÓXIMAS ATIVIDADES (inclui prazos vencidos)']
        lines += [f"{r['due']} · {r['kind']} · {r['subject']} · {r['title']}" for r in due] or ['Nenhuma atividade pendente.']
        lines += ['\nÚLTIMOS ARQUIVOS PROCESSADOS']
        lines += [f"{r['created']} · {r['status']} · {r['target']}" for r in files] or ['Nenhuma operação registrada.']
        lines += ['\nÚLTIMAS CALIBRAÇÕES']
        lines += [f"{r['name']} · {r['printer']} · {r['filament']} · bico {r['nozzle']} °C" for r in profiles]
        lines += [f"{r['created']} · {r['printer']} · {r['material']} · {r['temperature']} °C" for r in legacy]
        if not profiles and not legacy:
            lines += ['Nenhuma calibração registrada.']
        lines += ['\nEXECUÇÕES RECENTES DE SCRIPTS']
        lines += [f"{r['started']} · script #{r['script_id']} · saída {r['exit_code'] if r['finished'] else 'em andamento / interrompido sem resultado'}" for r in runs] or ['Nenhuma execução registrada.']
        self.dashboard_text.setPlainText('\n'.join(lines))
