import ctypes
import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit, urlunsplit


APP_TITLE = "Git Repository Pusher"
PROVIDERS = ("GitLab", "GitHub")

# The tool deliberately never performs a force push silently.
CONFLICT_SAFE = "safe"
CONFLICT_REPLACE = "replace"
CONFLICT_INTEGRATE = "integrate"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def find_git():
    return shutil.which("git")


def windows_unc_path(path):
    """Resolve a mapped Windows drive, for example Y:, to its UNC path."""
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
    """Run Git without a shell and return (return_code, combined_output)."""
    command = [find_git() or "git"]
    if cwd:
        safe_path = windows_unc_path(cwd)
        if safe_path:
            command.extend(["-c", f"safe.directory={safe_path}"])
    command.extend(args)

    try:
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
    except OSError as exc:
        return 1, str(exc)

    return completed.returncode, completed.stdout.strip()


def redact_url(value):
    """Hide credentials if a user accidentally enters them in a URL."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https", "ssh"} and parsed.username:
            hostname = parsed.hostname or ""
            if parsed.port:
                hostname += f":{parsed.port}"
            netloc = f"***:***@{hostname}"
            return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except ValueError:
        pass
    return value


def display_command(args):
    safe_args = [redact_url(str(arg)) for arg in args]
    if os.name == "nt":
        return "git " + " ".join(shlex.quote(arg) for arg in safe_args)
    return "git " + " ".join(shlex.quote(arg) for arg in safe_args)


def valid_ref_name(value):
    """Conservative validation for branch and tag names."""
    if not value or value.startswith("-"):
        return False
    if ".." in value or "@{" in value or "//" in value:
        return False
    if value.endswith("/") or value.endswith(".") or value.endswith(".lock"):
        return False
    if any(ord(char) < 32 for char in value):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._/\-]+", value))


def ref_exists(project, ref):
    code, _ = run_git(["show-ref", "--verify", "--quiet", ref], cwd=str(project))
    return code == 0


def is_ancestor(project, older, newer):
    code, _ = run_git(["merge-base", "--is-ancestor", older, newer], cwd=str(project))
    return code == 0


def has_common_base(project, first, second):
    code, _ = run_git(["merge-base", first, second], cwd=str(project))
    return code == 0


def parse_ls_remote_sha(output):
    for line in output.splitlines():
        parts = line.split()
        if parts and re.fullmatch(r"[0-9a-fA-F]{40,64}", parts[0]):
            return parts[0]
    return None


# ---------------------------------------------------------------------------
# Desktop application
# ---------------------------------------------------------------------------


class GitLabPusher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x760")
        self.minsize(760, 650)
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
        style.configure("Warning.TLabel", font=("Segoe UI", 9), foreground="#9b2c2c")
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 7))
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)

    def _build_ui(self):
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="Projekt zu GitLab oder GitHub pushen", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Lokale Dateien committen und sicher in einen vorhandenen oder neuen Branch pushen.",
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
        ttk.Label(repo_box, text="Plattform", width=22).grid(row=0, column=0, sticky="w", pady=5)
        provider = ttk.Combobox(
            repo_box,
            textvariable=self.provider_var,
            values=PROVIDERS,
            state="readonly",
            width=16,
        )
        provider.grid(row=0, column=1, sticky="w", pady=5)
        provider.bind("<<ComboboxSelected>>", self.provider_changed)
        self._entry_row(
            repo_box,
            "Repository-URL",
            self.repo_var,
            "HTTPS- oder SSH-Clone-URL",
            row=1,
        )
        self.repo_hint = ttk.Label(
            repo_box,
            text="GitLab: interne oder öffentliche Clone-URL. GitHub: github.com/<konto>/<repository>.git.",
            style="Subtitle.TLabel",
            wraplength=800,
        )
        self.repo_hint.grid(row=2, column=1, columnspan=2, sticky="w", pady=(7, 0))

        options_box = ttk.LabelFrame(outer, text="3. Commit, Branch und Tag", padding=14)
        options_box.pack(fill="x", pady=(0, 12))
        self.branch_var = tk.StringVar(value="main")
        self.message_var = tk.StringVar(value="Projekt aktualisiert")
        self.tag_var = tk.StringVar()
        self.tag_message_var = tk.StringVar()
        self._entry_row(options_box, "Ziel-Branch", self.branch_var, "main oder master", row=0)
        self._entry_row(options_box, "Commit-Nachricht", self.message_var, "z. B. Projekt aktualisiert", row=1)
        self._entry_row(options_box, "Tag (optional)", self.tag_var, "z. B. v1.0.0", row=2)
        self._entry_row(
            options_box,
            "Tag-Nachricht",
            self.tag_message_var,
            "leer = einfacher Tag; Text = annotierter Tag",
            row=3,
        )

        conflict_box = ttk.LabelFrame(outer, text="4. Verhalten bei abweichender Remote-Historie", padding=14)
        conflict_box.pack(fill="x", pady=(0, 12))
        self.conflict_var = tk.StringVar(value=CONFLICT_SAFE)
        conflict_values = (
            "Sicher abbrechen (keine Remote-Commits überschreiben)",
            "Remote-Branch ersetzen (mit --force-with-lease)",
            "Remote übernehmen und lokale Änderungen zusammenführen",
        )
        self.conflict_labels = {
            CONFLICT_SAFE: conflict_values[0],
            CONFLICT_REPLACE: conflict_values[1],
            CONFLICT_INTEGRATE: conflict_values[2],
        }
        self.conflict_codes = {label: code for code, label in self.conflict_labels.items()}
        conflict_combo = ttk.Combobox(
            conflict_box,
            textvariable=self.conflict_var,
            values=conflict_values,
            state="readonly",
        )
        conflict_combo.grid(row=0, column=0, sticky="ew")
        conflict_combo.set(conflict_values[0])
        conflict_box.columnconfigure(0, weight=1)
        ttk.Label(
            conflict_box,
            text=(
                "Für deinen Fall: „Remote-Branch ersetzen“ verwenden, wenn der Branch in GitLab/GitHub "
                "über die Weboberfläche geleert wurde und dein lokaler Ordner künftig der vollständige Stand sein soll."
            ),
            style="Subtitle.TLabel",
            wraplength=800,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            conflict_box,
            text=(
                "Die Option führt keinen unkontrollierten Force-Push aus. Der Remote-Stand wird zuerst gelesen; "
                "überschrieben wird nur, wenn er seitdem unverändert geblieben ist."
            ),
            style="Warning.TLabel",
            wraplength=800,
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 12))
        self.check_button = ttk.Button(actions, text="Verbindung prüfen", command=self.check_connection)
        self.check_button.pack(side="left")
        self.push_button = ttk.Button(
            actions,
            text="Commit erstellen und pushen",
            style="Accent.TButton",
            command=self.start_push,
        )
        self.push_button.pack(side="right")

        status_box = ttk.LabelFrame(outer, text="Status", padding=10)
        status_box.pack(fill="both", expand=True)
        text_frame = ttk.Frame(status_box)
        text_frame.pack(fill="both", expand=True)
        self.output = tk.Text(
            text_frame,
            height=14,
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
        ttk.Label(parent, text=label, width=22).grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        if placeholder:
            ttk.Label(parent, text=placeholder, style="Subtitle.TLabel").grid(
                row=row,
                column=2,
                sticky="w",
                padx=(10, 0),
            )
        parent.columnconfigure(1, weight=1)

    def _path_row(self, parent, variable, label, callback):
        ttk.Label(parent, text=label, width=22).grid(row=0, column=0, sticky="w")
        ttk.Entry(parent, textvariable=variable).grid(row=0, column=1, sticky="ew")
        ttk.Button(parent, text="Auswählen...", command=callback).grid(row=0, column=2, padx=(10, 0))
        parent.columnconfigure(1, weight=1)

    def provider_changed(self, _event=None):
        provider = self.provider_var.get()
        if provider == "GitHub":
            self.repo_hint.configure(
                text=(
                    "GitHub: github.com/<konto>/<repository>.git. Nutze HTTPS mit Git Credential Manager "
                    "oder SSH mit deinem GitHub-Schlüssel."
                )
            )
        else:
            self.repo_hint.configure(
                text=(
                    "GitLab: interne oder öffentliche Clone-URL. Nutze HTTPS oder SSH mit deiner lokalen "
                    "Git-Anmeldung."
                )
            )

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
        if not repo or not (
            repo.startswith("https://")
            or repo.startswith("http://")
            or repo.startswith("git@")
            or repo.startswith("ssh://")
        ):
            messagebox.showerror("Repository-URL fehlt", "Bitte trage die Clone-URL des Git-Repositories ein.")
            return None
        if not valid_ref_name(branch):
            messagebox.showerror(
                "Branch ungültig",
                "Der Branch enthält ungültige Git-Zeichen oder eine ungültige Struktur.",
            )
            return None
        if not message:
            messagebox.showerror("Commit-Nachricht fehlt", "Bitte trage eine Commit-Nachricht ein.")
            return None
        if tag and not valid_ref_name(tag):
            messagebox.showerror(
                "Tag ungültig",
                "Der Tag enthält ungültige Git-Zeichen oder eine ungültige Struktur.",
            )
            return None
        return project, repo, branch, message, tag, tag_message

    def _selected_conflict_mode(self):
        selected_label = self.conflict_var.get()
        return self.conflict_codes.get(selected_label, CONFLICT_SAFE)

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
        mode = self._selected_conflict_mode()
        action = "Lokale Änderungen committen und pushen"
        if tag:
            action += f" sowie Tag {tag} pushen"

        warning = ""
        if mode == CONFLICT_REPLACE:
            warning = (
                "\n\nACHTUNG: Wenn der Remote-Branch eine abweichende Historie enthält, "
                "wird er durch deinen lokalen Stand ersetzt. Das erfolgt geschützt mit "
                "--force-with-lease, nicht mit einem unkontrollierten --force."
            )
        elif mode == CONFLICT_INTEGRATE:
            warning = (
                "\n\nDer Remote-Branch wird bei Bedarf in deinen lokalen Branch zusammengeführt. "
                "Bei echten Konflikten bricht der Vorgang ab."
            )

        if not messagebox.askyesno(
            "Push bestätigen",
            f"{action} nach {self.provider_var.get()}?\n\nZiel: {branch}{warning}",
        ):
            return

        self._set_busy(True)
        self._log("Starte Push-Vorgang...")
        threading.Thread(
            target=self._worker_push,
            args=(project, repo, branch, message, tag, tag_message, mode),
            daemon=True,
        ).start()

    def _worker_push(self, project, repo, branch, message, tag, tag_message, mode):
        steps = []
        branch_ref = f"refs/heads/{branch}"
        remote_ref = f"refs/remotes/origin/{branch}"

        def run(args):
            code, output = run_git(args, cwd=str(project))
            steps.append((args, code, output))
            return code, output

        def fail():
            self.events.put(("push_done", steps, "failed"))

        if not (project / ".git").is_dir():
            code, _ = run(["init"])
            if code != 0:
                return fail()

        # Make origin point at the URL selected in the UI.
        code, remotes = run_git(["remote"], cwd=str(project))
        if code != 0:
            steps.append((["remote"], code, remotes))
            return fail()

        if "origin" in remotes.splitlines():
            code, _ = run(["remote", "set-url", "origin", repo])
        else:
            code, _ = run(["remote", "add", "origin", repo])
        if code != 0:
            return fail()

        # Read the remote branch before changing the local branch. This is the
        # missing step that caused the original 'fetch first' failure.
        code, remote_listing = run(["ls-remote", "--heads", "origin", branch_ref])
        if code != 0:
            return fail()
        remote_sha = parse_ls_remote_sha(remote_listing)

        if remote_sha:
            code, _ = run(
                [
                    "fetch",
                    "--prune",
                    "origin",
                    f"+{branch_ref}:{remote_ref}",
                ]
            )
            if code != 0:
                return fail()

        # Keep the existing user-facing behavior: the selected local folder is
        # made the source of the selected target branch.
        code, _ = run(["checkout", "-B", branch])
        if code != 0:
            return fail()

        code, _ = run(["add", "-A"])
        if code != 0:
            return fail()

        code, _ = run(["diff", "--cached", "--quiet"])
        if code == 1:
            code, _ = run(["commit", "-m", message])
            if code != 0:
                return fail()
        elif code != 0:
            return fail()

        code, local_sha_output = run(["rev-parse", "HEAD"])
        if code != 0:
            steps.append(
                (
                    ["rev-parse", "HEAD"],
                    1,
                    "Das lokale Repository enthält noch keinen Commit. Sind im Projektordner Dateien vorhanden?",
                )
            )
            return fail()
        local_sha = local_sha_output.splitlines()[-1].strip()

        needs_special_handling = False
        if remote_sha and remote_sha != local_sha:
            local_is_ancestor = is_ancestor(project, local_sha, remote_sha)
            remote_is_ancestor = is_ancestor(project, remote_sha, local_sha)
            needs_special_handling = not remote_is_ancestor

            if remote_is_ancestor:
                self._log_background(
                    f"Remote-{branch} ist Vorfahr des lokalen Stands; normaler Push ist möglich."
                )
            elif local_is_ancestor:
                self._log_background(
                    f"Remote-{branch} enthält zusätzliche Commits; normaler Push wäre nicht möglich."
                )
            else:
                self._log_background(
                    f"Lokaler und Remote-{branch} sind auseinanderentwickelt."
                )

            if needs_special_handling and mode == CONFLICT_SAFE:
                steps.append(
                    (
                        ["push", "-u", "origin", f"HEAD:{branch_ref}"],
                        1,
                        (
                            f"Push abgebrochen: Der Remote-Branch {branch} enthält einen anderen Stand. "
                            "Wähle bei Bedarf 'Remote-Branch ersetzen' oder 'Remote übernehmen und "
                            "lokale Änderungen zusammenführen'."
                        ),
                    )
                )
                return fail()

            if needs_special_handling and mode == CONFLICT_INTEGRATE:
                merge_args = ["merge", "--no-edit"]
                if not has_common_base(project, local_sha, remote_sha):
                    merge_args.append("--allow-unrelated-histories")
                merge_args.append(remote_ref)
                code, _ = run(merge_args)
                if code != 0:
                    abort_code, abort_output = run(["merge", "--abort"])
                    if abort_code != 0 and abort_output:
                        steps.append((["merge", "--abort"], abort_code, abort_output))
                    return fail()
                code, local_sha_output = run(["rev-parse", "HEAD"])
                if code != 0:
                    return fail()
                local_sha = local_sha_output.splitlines()[-1].strip()

        if needs_special_handling and mode == CONFLICT_REPLACE and remote_sha:
            push_args = [
                "push",
                f"--force-with-lease={branch_ref}:{remote_sha}",
                "-u",
                "origin",
                f"HEAD:{branch_ref}",
            ]
        else:
            push_args = ["push", "-u", "origin", f"HEAD:{branch_ref}"]

        code, _ = run(push_args)
        if code != 0:
            return fail()

        if tag:
            local_tag_exists = ref_exists(project, f"refs/tags/{tag}")
            steps.append(
                (
                    ["show-ref", "--verify", "--quiet", f"refs/tags/{tag}"],
                    0 if local_tag_exists else 1,
                    "Lokaler Tag existiert bereits." if local_tag_exists else "",
                )
            )
            if local_tag_exists:
                return self.events.put(("push_done", steps, "partial"))

            code, remote_tag_listing = run(["ls-remote", "--tags", "origin", f"refs/tags/{tag}"])
            if code != 0:
                return self.events.put(("push_done", steps, "partial"))
            if remote_tag_listing.strip():
                steps.append(
                    (
                        ["ls-remote", "--tags", "origin", f"refs/tags/{tag}"],
                        1,
                        f"Remote-Tag '{tag}' existiert bereits und wird nicht überschrieben.",
                    )
                )
                return self.events.put(("push_done", steps, "partial"))

            tag_args = ["tag", "-a", tag, "-m", tag_message] if tag_message else ["tag", tag]
            code, _ = run(tag_args)
            if code != 0:
                return self.events.put(("push_done", steps, "partial"))
            code, _ = run(["push", "origin", f"refs/tags/{tag}"])
            if code != 0:
                return self.events.put(("push_done", steps, "partial"))

        self.events.put(("push_done", steps, "success"))

    def _log_background(self, text):
        """Queue informational text so Tkinter is only touched on its UI thread."""
        self.events.put(("info", text))

    def _process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "info":
                    self._log(event[1])
                elif event[0] == "check_done":
                    _, code, output = event
                    if output:
                        self._log(output)
                    provider = self.provider_var.get()
                    if code == 0:
                        self._log(
                            f"Verbindung erfolgreich. {provider} akzeptiert die Repository-URL und deine lokale Anmeldung."
                        )
                    else:
                        self._log(
                            f"Verbindung fehlgeschlagen. Prüfe URL, Berechtigung sowie SSH- oder Windows-Git-Anmeldung für {provider}."
                        )
                    self._set_busy(False)
                elif event[0] == "push_done":
                    _, steps, status = event
                    for args, code, output in steps:
                        self._log(f"$ {display_command(args)}")
                        if output:
                            self._log(output)

                    if status == "success":
                        provider = self.provider_var.get()
                        self._log(f"Fertig: Das Projekt wurde erfolgreich zu {provider} gepusht.")
                        messagebox.showinfo("Push erfolgreich", f"Das Projekt wurde erfolgreich zu {provider} gepusht.")
                    elif status == "partial":
                        self._log(
                            "Der Branch wurde gepusht, aber der optionale Tag konnte nicht erstellt oder gepusht werden."
                        )
                        messagebox.showwarning(
                            "Push teilweise erfolgreich",
                            "Der Branch wurde gepusht. Beim optionalen Tag ist ein Fehler aufgetreten.",
                        )
                    else:
                        self._log("Push fehlgeschlagen. Die Ausgabe oben enthält die Git-Fehlermeldung.")
                        messagebox.showerror(
                            "Push fehlgeschlagen",
                            "Git konnte den Push nicht abschließen. Prüfe die Statusausgabe.",
                        )
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(100, self._process_events)


if __name__ == "__main__":
    app = GitLabPusher()
    app.mainloop()
