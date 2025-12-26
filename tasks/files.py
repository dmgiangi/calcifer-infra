import hashlib

from nornir.core.task import Task, Result
from nornir_scrapli.tasks import send_command

from tasks.utils import run_local


def _read_file(task: Task, path: str) -> str:
    """Legge un file remoto o locale e ritorna il contenuto."""
    cmd = f"sudo cat {path}"

    if task.host.platform == "linux_local":
        res = task.run(task=run_local, command=cmd)
    else:
        res = task.run(task=send_command, command=cmd)

    if res.failed:
        # Se il file non esiste, ritorniamo stringa vuota (o gestiamo diversamente)
        return ""
    return res.result


def _write_file(task: Task, path: str, content: str) -> Result:
    """
    Scrive il contenuto su un file remoto (usando tee per i permessi sudo).
    Ritorna un Result che indica se è stato cambiato o no.
    """
    # 1. Calcola hash del nuovo contenuto
    new_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

    # 2. Leggi contenuto attuale (per idempotenza)
    current_content = _read_file(task, path)
    current_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()

    if new_hash == current_hash:
        return Result(host=task.host, changed=False, result="File is up to date")

    # 3. Scrittura (usiamo una tecnica sicura con heredoc e quote per evitare injection)
    # Esempio: cat << 'EOF' > file ...
    # Attenzione: bisogna gestire i caratteri speciali nel content.
    # Un metodo robusto per file piccoli/medi è usare printf o base64 per evitare problemi di escaping.

    # Usiamo base64 per evitare qualsiasi problema di escaping bash
    import base64
    b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

    # Comando: decodifica base64 e scrivi su file tramite tee
    cmd = f"echo '{b64_content}' | base64 -d | sudo tee {path} > /dev/null"

    if task.host.platform == "linux_local":
        res = task.run(task=run_local, command=cmd)
    else:
        res = task.run(task=send_command, command=cmd)

    return Result(host=task.host, changed=True, result="File updated", failed=res.failed)


def ensure_line_in_file(task: Task, path: str, line: str, match_regex: str = None) -> Result:
    """
    Assicura che una riga sia presente.
    Se match_regex è fornito, sostituisce la riga che matcha.
    Altrimenti appende in fondo.
    """
    import re

    content = _read_file(task, path)
    lines = content.splitlines()
    new_lines = []
    found = False

    if match_regex:
        regex = re.compile(match_regex)
        for l in lines:
            if regex.search(l):
                new_lines.append(line)  # Sostituisci
                found = True
            else:
                new_lines.append(l)  # Mantieni
        if not found:
            new_lines.append(line)  # Aggiungi se non trovato
    else:
        # Ricerca esatta
        if line in lines:
            return Result(host=task.host, changed=False, result="Line already exists")
        new_lines = lines + [line]

    final_content = "\n".join(new_lines) + "\n"  # Ensure trailing newline

    return _write_file(task, path, final_content)
