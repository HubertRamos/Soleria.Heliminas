"""Relatórios locais em HTML gerados a partir das pesquisas."""

from soleria.reports.format import formatar_candidatos, formatar_relatorio
from soleria.reports.model import Relatorio
from soleria.reports.store import RepositorioRelatorios

__all__ = [
    "Relatorio",
    "RepositorioRelatorios",
    "formatar_candidatos",
    "formatar_relatorio",
]
