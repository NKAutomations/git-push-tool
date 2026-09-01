import ctypes
import os
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Git Repository Pusher"
DEFAULT_GITLAB_HOST = "https://gitlab.k8s.nobilia.de"


PROVIDERS = ("GitLab", "GitHub")


def find_git():
    return shutil.which("git")


def windows_unc_path(path):
    """Resolve a mapped Windows drive (for example Y:) to its UNC path."""
    if os.name != "nt":
        return None

    full_path = os.path.abspath(os.fspath(path))
    drive, tail = os.path.splitdrive(full_path)
    if not drive or not drive.endswith(":"):
        return full_path if full_path.startswith("\\\\") else None

    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(len(buffer))
        result = ctypes.windll.mpr.WNetGetConnectionW(
            drive,
            buffer,
            ctypes.byref(size),
        )
        if result == 0 and buffer.value:
            return buffer.value.rstrip("\\/") + tail.replace("/", "\\")
    except (AttributeError, OSError):
        pass
    return None


def run_git(args, cwd=None, env=None):
    command = [find_git() or "git"]
    if cwd:
        safe_path = windows_unc_path(cwd)
        if safe_path:
            # Git may canonicalize mapped drives to UNC paths before checking
            # safe.directory. Pass the exact resolved path for this command only.
            command.extend(["-c", f"safe.directory={safe_path}"])
    command.extend(args)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    return completed.returncode, completed.stdout.strip()


def is_valid_branch(branch):
    if not branch or branch.startswith("-") or ".." in branch or " " in branch:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._/\-]+", branch))


def is_valid_tag(tag):
    if not tag or tag.startswith("-") or ".." in tag or any(ord(char) < 32 for char in tag):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._/\-]+", tag))


def is_valid_tag(tag):
    if not tag or tag.startswith("-") or ".." in tag or any(ord(char) < 32 for char in tag):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._/\-]+", tag))


class GitLabPusher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("830x650")
        self.minsize(720, 560)
        self.configure(bg="#f4f6f8")
        self.events = queue.Queue()
        self.busy = False
        self._build_style()
        self._build_ui()
        self.after(100, self._process_events)
        self._check_git()

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#17202a")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#5b6770")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#17202a")
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 7))
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)

    def _build_ui(self):
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 20))
        ttk.Label(header, text="Projekt zu GitLab oder GitHub pushen", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Ein lokales Werkzeug für VS-Code-Projekte, Branches und optionale Release-Tags.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        project_box = ttk.LabelFrame(outer, text="1. Lokales Projekt", padding=14)
        project_box.pack(fill="x", pady=(0, 12))
        self.project_var = tk.StringVar()
        self._path_row(project_box, self.project_var, "Projektordner", self.choose_project)

        repo_box = ttk.LabelFrame(outer, text="2. Zielplattform und Repository", padding=14)
        repo_box.pack(fill="x", pady=(0, 12))
        self.provider_var = tk.StringVar(value="GitLab")
        self.repo_var = tk.StringVar()
        ttk.Label(repo_box, text="Plattform", width=19).grid(row=0, column=0, sticky="w", pady=5)
        provider = ttk.Combobox(repo_box, textvariable=self.provider_var, values=PROVIDERS, state="readonly", width=16)
        provider.grid(row=0, column=1, sticky="w", pady=5)
        provider.bind("<<ComboboxSelected>>", self.provider_changed)
        self._entry_row(repo_box, "Repository-URL", self.repo_var, "HTTPS- oder SSH-Clone-URL", row=1)
        self.repo_hint = ttk.Label(
            repo_box,
            text="GitLab: interne nobilia-URL. GitHub: github.com/<konto>/<repository>.git. Git nutzt deine lokale Anmeldung.",
            style="Subtitle.TLabel",
            wraplength=740,
        )
        self.repo_hint.grid(row=2, column=1, columnspan=2, sticky="w", pady=(7, 0))

        options_box = ttk.LabelFrame(outer, text="3. Commit, Branch und Tag", padding=14)
        options_box.pack(fill="x", pady=(0, 12))
        self.branch_var = tk.StringVar(value="main")
        self.message_var = tk.StringVar(value="Projekt initial angelegt")
        self.tag_var = tk.StringVar()
        self.tag_message_var = tk.StringVar()
        self._entry_row(options_box, "Ziel-Branch", self.branch_var, "main", row=0)
        self._entry_row(options_box, "Commit-Nachricht", self.message_var, "z. B. Projekt initial angelegt", row=1)
        self._entry_row(options_box, "Tag (optional)", self.tag_var, "z. B. v1.0.0", row=2)
        self._entry_row(options_box, "Tag-Nachricht", self.tag_message_var, "leer = einfacher Tag; Text = annotierter Tag", row=3)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 12))
        self.check_button = ttk.Button(actions, text="Verbindung prüfen", command=self.check_connection)
        self.check_button.pack(side="left")
        self.push_button = ttk.Button(actions, text="Commit erstellen und pushen", style="Accent.TButton", command=self.start_push)
        self.push_button.pack(side="right")

        status_box = ttk.LabelFrame(outer, text="Status", padding=10)
        status_box.pack(fill="both", expand=True)
        text_frame = ttk.Frame(status_box)
        text_frame.pack(fill="both", expand=True)
        self.output = tk.Text(
            text_frame,
            height=12,
            wrap="word",
            font=("Cascadia Mono", 9),
            bg="#17202a",
            fg="#e8edf0",
            insertbackground="#ffffff",
            relief="flat",
            padx=12,
            pady=10,
        )
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._log("Bereit. Wähle einen Projektordner, eine Plattform und die Clone-URL des Repositories aus.")

        footer = ttk.Label(
            outer,
            text="Sicherheit: Das Tool fragt kein Passwort ab und schreibt keinen Token in die Repository-URL.",
            style="Subtitle.TLabel",
        )
        footer.pack(anchor="w", pady=(10, 0))

    def _entry_row(self, parent, label, variable, placeholder="", row=0):
        ttk.Label(parent, text=label, width=19).grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        if placeholder:
            ttk.Label(parent, text=placeholder, style="Subtitle.TLabel").grid(row=row, column=2, sticky="w", padx=(10, 0))
        parent.columnconfigure(1, weight=1)

    def _path_row(self, parent, variable, label, callback):
        ttk.Label(parent, text=label, width=19).grid(row=0, column=0, sticky="w")
        ttk.Entry(parent, textvariable=variable).grid(row=0, column=1, sticky="ew")
        ttk.Button(parent, text="Auswählen...", command=callback).grid(row=0, column=2, padx=(10, 0))
        parent.columnconfigure(1, weight=1)

    def provider_changed(self, _event=None):
        provider = self.provider_var.get()
        if provider == "GitHub":
            self.repo_hint.configure(text="GitHub: github.com/<konto>/<repository>.git. Nutze HTTPS mit Git Credential Manager oder SSH mit deinem GitHub-Schlüssel.")
        else:
            self.repo_hint.configure(text="GitLab: interne nobilia-URL. Nutze HTTPS oder SSH mit deiner lokalen Git-Anmeldung.")

    def _check_git(self):
        git = find_git()
        if git:
            self._log(f"Git gefunden: {git}")
        else:
            self._log("Git wurde nicht gefunden. Installiere Git for Windows und starte das Tool danach erneut.")
            self.push_button.configure(state="disabled")
            self.check_button.configure(state="disabled")

    def choose_project(self):
        folder = filedialog.askdirectory(title="VS-Code-Projektordner auswählen")
        if folder:
            self.project_var.set(folder)
            self._log(f"Projektordner ausgewählt: {folder}")

    def _log(self, text):
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.check_button.configure(state=state)
        self.push_button.configure(state=state)

    def _validate(self):
        project = Path(self.project_var.get().strip())
        repo = self.repo_var.get().strip()
        branch = self.branch_var.get().strip()
        message = self.message_var.get().strip()
        tag = self.tag_var.get().strip()
        tag_message = self.tag_message_var.get().strip()
        if not project.is_dir():
            messagebox.showerror("Projektordner fehlt", "Bitte wähle einen gültigen lokalen Projektordner aus.")
            return None
        if not repo or not (repo.startswith("https://") or repo.startswith("http://") or repo.startswith("git@") or repo.startswith("ssh://")):
            messagebox.showerror("Repository-URL fehlt", "Bitte trage die Clone-URL des Git-Repositories ein.")
            return None
        if not is_valid_branch(branch):
            messagebox.showerror("Branch ungültig", "Der Branch darf nur normale Git-Zeichen enthalten und keine Leerzeichen oder '..'.")
            return None
        if not message:
            messagebox.showerror("Commit-Nachricht fehlt", "Bitte trage eine Commit-Nachricht ein.")
            return None
        if tag and not is_valid_tag(tag):
            messagebox.showerror("Tag ungültig", "Der Tag darf keine Leerzeichen, '..' oder Steuerzeichen enthalten.")
            return None
        return project, repo, branch, message, tag, tag_message

    def check_connection(self):
        values = self._validate()
        if not values or self.busy:
            return
        _, repo, _, _, _, _ = values
        self._set_busy(True)
        self._log(f"Prüfe {self.provider_var.get()}-Repository...")
        threading.Thread(target=self._worker_check, args=(repo,), daemon=True).start()

    def _worker_check(self, repo):
        code, output = run_git(["ls-remote", "--heads", repo])
        self.events.put(("check_done", code, output))

    def start_push(self):
        values = self._validate()
        if not values or self.busy:
            return
        project, repo, branch, message, tag, tag_message = values
        action = "Commit erstellen und pushen"
        if tag:
            action += f" sowie Tag {tag} pushen"
        if not messagebox.askyesno(
            "Push bestätigen",
            f"Alle Dateien im ausgewählten Projektordner werden zu {self.provider_var.get()} hinzugefügt und in das angegebene Repository gepusht.\n\n{action}?",
        ):
            return
        self._set_busy(True)
        self._log("Starte Push-Vorgang...")
        threading.Thread(target=self._worker_push, args=(project, repo, branch, message, tag, tag_message), daemon=True).start()

    def _worker_push(self, project, repo, branch, message, tag, tag_message):
        steps = []

        def run(args):
            code, output = run_git(args, cwd=str(project))
            steps.append((args, code, output))
            return code

        if not (project / ".git").is_dir():
            if run(["init"]) != 0:
                return self.events.put(("push_done", steps, False))

        # Make sure the target is known and points at the requested URL.
        code, remotes = run_git(["remote"], cwd=str(project))
        if code != 0:
            steps.append((["remote"], code, remotes))
            return self.events.put(("push_done", steps, False))
        if "origin" in remotes.splitlines():
            run(["remote", "set-url", "origin", repo])
        else:
            run(["remote", "add", "origin", repo])
        if steps[-1][1] != 0:
            return self.events.put(("push_done", steps, False))

        if run(["checkout", "-B", branch]) != 0:
            return self.events.put(("push_done", steps, False))
        if run(["add", "-A"]) != 0:
            return self.events.put(("push_done", steps, False))

        code, staged = run_git(["diff", "--cached", "--quiet"], cwd=str(project))
        steps.append((["diff", "--cached", "--quiet"], code, staged))
        if code == 0:
            # There are no staged changes. A push may still be useful if commits exist.
            code_log, log = run_git(["log", "-1", "--oneline"], cwd=str(project))
            steps.append((["log", "-1", "--oneline"], code_log, log))
            if code_log != 0:
                return self.events.put(("push_done", steps, False))
        else:
            if run(["commit", "-m", message]) != 0:
                return self.events.put(("push_done", steps, False))

        if run(["push", "-u", "origin", branch]) != 0:
            return self.events.put(("push_done", steps, False))

        if tag:
            # Do not overwrite an existing tag silently.
            code_tag, tag_output = run_git(["rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cwd=str(project))
            steps.append((["rev-parse", "-q", "--verify", f"refs/tags/{tag}"], code_tag, tag_output))
            if code_tag == 0:
                steps.append((["tag", tag], 1, f"Tag '{tag}' existiert lokal bereits und wird nicht überschrieben."))
                return self.events.put(("push_done", steps, False))
            tag_args = ["tag", "-a", tag, "-m", tag_message] if tag_message else ["tag", tag]
            if run(tag_args) != 0:
                return self.events.put(("push_done", steps, False))
            if run(["push", "origin", f"refs/tags/{tag}"]) != 0:
                return self.events.put(("push_done", steps, False))

        self.events.put(("push_done", steps, True))

    def _process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "check_done":
                    _, code, output = event
                    if output:
                        self._log(output)
                    provider = self.provider_var.get()
                    if code == 0:
                        self._log(f"Verbindung erfolgreich. {provider} akzeptiert die Repository-URL und deine lokale Anmeldung.")
                    else:
                        self._log(f"Verbindung fehlgeschlagen. Prüfe URL, Berechtigung sowie SSH- oder Windows-Git-Anmeldung für {provider}.")
                    self._set_busy(False)
                elif event[0] == "push_done":
                    _, steps, success = event
                    for args, code, output in steps:
                        command = "git " + " ".join(args)
                        self._log(f"$ {command}")
                        if output:
                            self._log(output)
                    if success:
                        provider = self.provider_var.get()
                        self._log(f"Fertig: Das Projekt wurde erfolgreich zu {provider} gepusht.")
                        messagebox.showinfo("Push erfolgreich", f"Das Projekt wurde erfolgreich zu {provider} gepusht.")
                    else:
                        self._log("Push fehlgeschlagen. Die Ausgabe oben enthält die Git-Fehlermeldung.")
                        messagebox.showerror("Push fehlgeschlagen", "Git konnte den Push nicht abschließen. Prüfe die Statusausgabe.")
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(100, self._process_events)


if __name__ == "__main__":
    app = GitLabPusher()
    app.mainloop()
