from rich.console import Console
from rich.theme import Theme


class ArcLogger:
    def __init__(self):
        # 1. Definizione del tema colori personalizzato
        self.custom_theme = Theme({
            "success": "bold green",
            "error": "bold red",
            "skip": "bold cyan",
            "warning": "bold yellow",
            "info": "dim white"
        })
        # Inizializziamo la Console di Rich con il nostro tema
        self.console = Console(theme=self.custom_theme)

        # Variabile per tenere traccia della profondità (indentazione)
        self.indent_level = 0

    def log_step(self, status: str, msg: str):
        """
        Stampa una riga di log dello step corrente.
        Usa l'indentazione attuale e l'icona appropriata.
        """
        icons = {
            "success": "✅",
            "error": "❌",
            "skip": "🔵",
            "warning": "🔶",
            "info": "ℹ️"
        }
        # Default a pallino se lo status non esiste
        icon = icons.get(status, "•")

        # Calcolo lo spazio vuoto a sinistra basato sul livello
        indent = "   " * self.indent_level

        # Stampa formattata: {spazio} {icona} [colore]{messaggio}[/colore]
        self.console.print(f"{indent}{icon} [{status}]{msg}[/{status}]")

    def workflow(self, name: str):
        """Restituisce il context manager per un Workflow (livello top)"""
        return self._Context(self, name, type="workflow")

    def task(self, name: str):
        """Restituisce il context manager per un Task (livello annidato)"""
        return self._Context(self, name, type="task")

    # --- Classe Interna (The Context Manager) ---
    class _Context:
        def __init__(self, logger, name, type):
            self.logger = logger
            self.name = name
            self.type = type

        def __enter__(self):
            # Eseguito all'inizio del 'with'
            indent = "   " * self.logger.indent_level

            if self.type == "workflow":
                self.logger.console.print(f"\n{indent}🚀 [bold blue]Workflow: {self.name}[/bold blue]")
            else:
                self.logger.console.print(f"{indent}🔸 [bold white]Task: {self.name}[/bold white]")

            # AUMENTA l'indentazione per i comandi successivi
            self.logger.indent_level += 1
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            # Eseguito alla fine del 'with' (anche se c'è errore)

            # DIMINUISCE l'indentazione
            self.logger.indent_level -= 1

            # Se c'è stata un'eccezione non gestita dentro il blocco, la logghiamo
            if exc_type:
                self.logger.log_step("error", f"Interrotto da errore: {exc_value}")
                # Ritorniamo False per lasciare che l'errore fermi il programma
                return False


logger = ArcLogger()