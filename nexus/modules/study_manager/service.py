"""Validações acadêmicas independentes de Qt."""
from datetime import datetime


def validate_activity(values):
    datetime.strptime(values[3], '%Y-%m-%d')
    if values[2] not in {'Tarefa', 'Prova', 'Trabalho', 'Exercícios', 'Compromisso'}:
        raise ValueError('Tipo de atividade desconhecido.')
    if values[4] not in (0, 1):
        raise ValueError('Estado de conclusão inválido.')
