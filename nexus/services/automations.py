from pathlib import Path
from nexus.services.files import plan_copy, execute_copy


class Automations:
    """Regras persistidas, executadas manualmente com prévia obrigatória na UI."""
    def __init__(self, db):
        self.db = db

    def save(self, source, destination, extension=""):
        plan_copy(Path(source), Path(destination), extension)
        return self.db.execute("INSERT INTO automations(source,destination,extension) VALUES(?,?,?)",
                               (str(Path(source).resolve()), str(Path(destination).resolve()), extension.strip().lower()))

    def plan(self, rule):
        return plan_copy(Path(rule["source"]), Path(rule["destination"]), rule["extension"])

    def run(self, rule, plan, *, continue_on_error=False):
        # Rebuild the rule's plan to reject stale previews or unrelated caller-supplied targets.
        if self.plan(rule) != plan:
            raise ValueError("A pasta mudou; gere uma nova prévia.")
        from nexus.services.manager import FileManager
        copied = FileManager(self.db).copy(plan, continue_on_error=continue_on_error)
        self.db.execute("INSERT INTO runs(automation_id,copied) VALUES(?,?)", (rule["id"], copied.completed if continue_on_error else copied))
        return copied
