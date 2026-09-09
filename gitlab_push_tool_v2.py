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
CONFLICT_SAFE = "safe"
CONFLICT_REPLACE = "replace"
CONFLICT_INTEGRATE = "integrate"


def find_git():
    return shutil.which("git")


def windows_unc_path(path):
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
            drive, buffer, ctypes.byref(size)
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
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https", "ssh"} and parsed.username:
            hostname = parsed.hostname or ""
            if parsed.port:
                hostname += f":{parsed.port}"
            return urlunsplit(
                (parsed.scheme, "***:***@" + hostname, parsed.path, parsed.query, parsed.fragment)
            )
    except ValueError:
        pass
    return value


def display_command(args):
    return "git " + " ".join(shlex.quote(redact_url(str(arg))) for arg in args)


def valid_ref_name(value):
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


class ScrollableFrame(ttk.Frame):
    """Canvas-based vertical scrolling that keeps the content width in sync."""

    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(
            self, background="#f4f6f8", borderwidth=0, highlightthickness=0
        )
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.inner = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", self._update_scrollregion)
        self.canvas.bind("<Configure>", self._fit_width)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        self.inner.bind("<Enter>", self._bind_wheel)
        self.inner.bind("<Leave>", self._unbind_wheel)

    def _update_scrollregion(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _fit_width(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _bind_wheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.canvas.bind_all("<Button-4>", self._on_wheel, add="+")
        self.canvas.bind_all("<Button-5>", self._on_wheel, add="+")

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        if getattr(event, "num", None) == 4:
            amount = -1
        elif getattr(event, "num", None) == 5:
            amount = 1
        else:
            amount = -int(event.delta / 120) if event.delta else 0
        if amount:
            self.canvas.yview_scroll(amount, "units")


class GitLabPusher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("960x820")
        self.minsize(420, 540)
        self.configure(bg="#f4f6f8")
        self.events = queue.Queue()
        self.busy = False
        self.compact_layout = None
        self.form_rows = []
        self._build_style()
        self._build_ui()
        self.bind("<Configure>", self._on_resize)
        self.after(100, self._process_events)
        self._check_git()
        self.after_idle(lambda: self._apply_layout(self.winfo_width()))

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#17202a")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#5b6770")
        style.configure("Warning.TLabel", font=("Segoe UI", 9), foreground="#9b2c2c")
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 7))
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)

    def _build_ui(self):
        self.scroller = ScrollableFrame(self)
        self.scroller.pack(fill="both", expand=True)
        outer = ttk.Frame(self.scroller.inner, padding=16)
        outer.pack(fill="x", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 16))
        self.title_label = ttk.Label(
            header, text="Projekt zu GitLab oder GitHub pushen", style="Title.TLabel"
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = ttk.Label(
            header,
            text="Lokale Dateien committen und sicher in einen vorhandenen oder neuen Branch pushen.",
            style="Subtitle.TLabel",
            justify="left",
            anchor="w",
        )
        self.subtitle_label.pack(fill="x", pady=(4, 0))

        project_box = ttk.LabelFrame(outer, text="1. Lokales Projekt", padding=12)
        project_box.pack(fill="x", pady=(0, 10))
        self.project_var = tk.StringVar()
        self._path_row(project_box, "Projektordner", self.project_var, self.choose_project)

        repo_box = ttk.LabelFrame(outer, text="2. Zielplattform und Repository", padding=12)
        repo_box.pack(fill="x", pady=(0, 10))
        self.provider_var = tk.StringVar(value="GitLab")
        self.repo_var = tk.StringVar()
        self._provider_row(repo_box)
        self._entry_row(repo_box, "Repository-URL", self.repo_var, "HTTPS- oder SSH-Clone-URL")
        self.repo_hint = ttk.Label(
            repo_box,
            text="GitLab: interne oder oeffentliche Clone-URL. GitHub: github.com/<konto>/<repository>.git.",
            style="Subtitle.TLabel",
            justify="left",
            anchor="w",
        )
        self.repo_hint.pack(fill="x", pady=(5, 0))

        options_box = ttk.LabelFrame(outer, text="3. Commit, Branch und Tag", padding=12)
        options_box.pack(fill="x", pady=(0, 10))
        self.branch_var = tk.StringVar(value="main")
        self.message_var = tk.StringVar(value="Projekt aktualisiert")
        self.tag_var = tk.StringVar()
        self.tag_message_var = tk.StringVar()
        self._entry_row(options_box, "Ziel-Branch", self.branch_var, "main oder master")
        self._entry_row(options_box, "Commit-Nachricht", self.message_var, "z. B. Projekt aktualisiert")
        self._entry_row(options_box, "Tag (optional)", self.tag_var, "z. B. v1.0.0")
        self._entry_row(options_box, "Tag-Nachricht", self.tag_message_var, "leer = einfacher Tag; Text = annotierter Tag")

        conflict_box = ttk.LabelFrame(
            outer, text="4. Verhalten bei abweichender Remote-Historie", padding=12
        )
        conflict_box.pack(fill="x", pady=(0, 10))
        self.conflict_var = tk.StringVar()
        conflict_values = (
            "Sicher abbrechen (keine Remote-Commits ueberschreiben)",
            "Remote-Branch ersetzen (mit --force-with-lease)",
            "Remote uebernehmen und lokale Aenderungen zusammenfuehren",
        )
        self.conflict_labels = {
            CONFLICT_SAFE: conflict_values[0],
            CONFLICT_REPLACE: conflict_values[1],
            CONFLICT_INTEGRATE: conflict_values[2],
        }
        self.conflict_codes = {label: code for code, label in self.conflict_labels.items()}
        self.conflict_combo = ttk.Combobox(
            conflict_box, textvariable=self.conflict_var, values=conflict_values, state="readonly"
        )
        self.conflict_combo.pack(fill="x")
        self.conflict_combo.set(conflict_values[0])
        self.conflict_hint = ttk.Label(
            conflict_box,
            text="Fuer deinen Fall: 'Remote-Branch ersetzen' verwenden, wenn der Branch in GitLab/GitHub ueber die Weboberflaeche geleert wurde und dein lokaler Ordner kuenftig der vollstaendige Stand sein soll.",
            style="Subtitle.TLabel",
            justify="left",
            anchor="w",
        )
        self.conflict_hint.pack(fill="x", pady=(6, 0))
        self.conflict_warning = ttk.Label(
            conflict_box,
            text="Die Option fuehrt keinen unkontrollierten Force-Push aus. Der Remote-Stand wird zuerst gelesen; ueberschrieben wird nur, wenn er seitdem unveraendert geblieben ist.",
            style="Warning.TLabel",
            justify="left",
            anchor="w",
        )
        self.conflict_warning.pack(fill="x", pady=(4, 0))

        self.actions = ttk.Frame(outer)
        self.actions.pack(fill="x", pady=(0, 10))
        self.check_button = ttk.Button(self.actions, text="Verbindung pruefen", command=self.check_connection)
        self.push_button = ttk.Button(
            self.actions, text="Commit erstellen und pushen", style="Accent.TButton", command=self.start_push
        )

        status_box = ttk.LabelFrame(outer, text="Status", padding=8)
        status_box.pack(fill="x")
        text_frame = ttk.Frame(status_box)
        text_frame.pack(fill="x", expand=True)
        self.output = tk.Text(
            text_frame,
            height=10,
            wrap="word",
            font=("Cascadia Mono", 9),
            bg="#17202a",
            fg="#e8edf0",
            insertbackground="#ffffff",
            relief="flat",
            padx=10,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._log("Bereit. Waehle einen Projektordner, eine Plattform und die Clone-URL des Repositories aus.")

        self.footer = ttk.Label(
            outer,
            text="Sicherheit: Das Tool fragt kein Passwort ab und schreibt keinen Token in die Repository-URL.",
            style="Subtitle.TLabel",
            justify="left",
            anchor="w",
        )
        self.footer.pack(fill="x", pady=(8, 0))

    def _register_row(self, row, label, control, helper=None):
        self.form_rows.append((row, label, control, helper))

    def _entry_row(self, parent, label_text, variable, helper_text):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        label = ttk.Label(row, text=label_text)
        control = ttk.Entry(row, textvariable=variable)
        helper = ttk.Label(row, text=helper_text, style="Subtitle.TLabel", justify="left", anchor="w")
        self._register_row(row, label, control, helper)

    def _provider_row(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        label = ttk.Label(row, text="Plattform")
        control = ttk.Combobox(row, textvariable=self.provider_var, values=PROVIDERS, state="readonly")
        control.bind("<<ComboboxSelected>>", self.provider_changed)
        self._register_row(row, label, control)

    def _path_row(self, parent, label_text, variable, callback):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        label = ttk.Label(row, text=label_text)
        control = ttk.Entry(row, textvariable=variable)
        button = ttk.Button(row, text="Auswaehlen...", command=callback)
        self._register_row(row, label, control, button)

    def _apply_layout(self, width):
        if width < 100:
            return
        compact = width < 740
        changed = compact != self.compact_layout
        self.compact_layout = compact
        wrap_width = max(240, width - 48)

        for row, label, control, helper in self.form_rows:
            for widget in (label, control, helper):
                if widget:
                    widget.grid_forget()
            row.columnconfigure(0, weight=0)
            row.columnconfigure(1, weight=0)
            if compact:
                row.columnconfigure(0, weight=1)
                label.grid(row=0, column=0, sticky="w")
                control.grid(row=1, column=0, sticky="ew", pady=(3, 0))
                if helper:
                    if isinstance(helper, ttk.Button):
                        helper.grid(row=2, column=0, sticky="ew", pady=(4, 0))
                    else:
                        helper.configure(wraplength=wrap_width)
                        helper.grid(row=2, column=0, sticky="w", pady=(2, 0))
            else:
                row.columnconfigure(1, weight=1)
                label.grid(row=0, column=0, sticky="w")
                control.grid(row=0, column=1, sticky="ew", padx=(12, 0))
                if helper:
                    if isinstance(helper, ttk.Button):
                        helper.grid(row=0, column=2, sticky="ew", padx=(10, 0))
                    else:
                        helper.configure(wraplength=max(220, width - 560))
                        helper.grid(row=0, column=2, sticky="w", padx=(10, 0))

        for widget in (self.repo_hint, self.conflict_hint, self.conflict_warning, self.footer, self.subtitle_label):
            widget.configure(wraplength=wrap_width)

        self.actions.columnconfigure(0, weight=1 if compact else 0)
        self.actions.columnconfigure(1, weight=1)
        self.check_button.grid_forget()
        self.push_button.grid_forget()
        if compact:
            self.check_button.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
            self.push_button.grid(row=1, column=0, columnspan=2, sticky="ew")
        else:
            self.check_button.grid(row=0, column=0, sticky="w")
            self.push_button.grid(row=0, column=1, sticky="e")

        if changed:
            self.scroller.after_idle(self.scroller._update_scrollregion)

    def _on_resize(self, event):
        if event.widget is self:
            self._apply_layout(event.width)

    def provider_changed(self, _event=None):
        if self.provider_var.get() == "GitHub":
            self.repo_hint.configure(
                text="GitHub: github.com/<konto>/<repository>.git. Nutze HTTPS mit Git Credential Manager oder SSH mit deinem GitHub-Schluessel."
            )
        else:
            self.repo_hint.configure(
                text="GitLab: interne oder oeffentliche Clone-URL. Nutze HTTPS oder SSH mit deiner lokalen Git-Anmeldung."
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
        folder = filedialog.askdirectory(title="VS-Code-Projektordner auswaehlen")
        if folder:
            self.project_var.set(folder)
            self._log(f"Projektordner ausgewaehlt: {folder}")

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
            messagebox.showerror("Projektordner fehlt", "Bitte waehle einen gueltigen lokalen Projektordner aus.")
            return None
        if not repo or not (repo.startswith("https://") or repo.startswith("http://") or repo.startswith("git@") or repo.startswith("ssh://")):
            messagebox.showerror("Repository-URL fehlt", "Bitte trage die Clone-URL des Git-Repositories ein.")
            return None
        if not valid_ref_name(branch):
            messagebox.showerror("Branch ungueltig", "Der Branch enthaelt ungueltige Git-Zeichen oder eine ungueltige Struktur.")
            return None
        if not message:
            messagebox.showerror("Commit-Nachricht fehlt", "Bitte trage eine Commit-Nachricht ein.")
            return None
        if tag and not valid_ref_name(tag):
            messagebox.showerror("Tag ungueltig", "Der Tag enthaelt ungueltige Git-Zeichen oder eine ungueltige Struktur.")
            return None
        return project, repo, branch, message, tag, tag_message

    def _selected_conflict_mode(self):
        return self.conflict_codes.get(self.conflict_var.get(), CONFLICT_SAFE)

    def check_connection(self):
        values = self._validate()
        if not values or self.busy:
            return
        _, repo, _, _, _, _ = values
        self._set_busy(True)
        self._log(f"Pruefe {self.provider_var.get()}-Repository...")
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
        warning = ""
        if mode == CONFLICT_REPLACE:
            warning = "\n\nACHTUNG: Eine abweichende Remote-Historie wird geschuetzt mit --force-with-lease ersetzt."
        elif mode == CONFLICT_INTEGRATE:
            warning = "\n\nDer Remote-Branch wird bei Bedarf lokal zusammengefuehrt. Bei echten Konflikten bricht der Vorgang ab."
        action = "Lokale Aenderungen committen und pushen"
        if tag:
            action += f" sowie Tag {tag} pushen"
        if not messagebox.askyesno(
            "Push bestaetigen",
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
        code, remote_listing = run(["ls-remote", "--heads", "origin", branch_ref])
        if code != 0:
            return fail()
        remote_sha = parse_ls_remote_sha(remote_listing)
        if remote_sha:
            code, _ = run(["fetch", "--prune", "origin", f"+{branch_ref}:{remote_ref}"])
            if code != 0:
                return fail()
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
            steps.append((["rev-parse", "HEAD"], 1, "Das lokale Repository enthaelt noch keinen Commit."))
            return fail()
        local_sha = local_sha_output.splitlines()[-1].strip()
        needs_special_handling = False
        if remote_sha and remote_sha != local_sha:
            local_is_ancestor = is_ancestor(project, local_sha, remote_sha)
            remote_is_ancestor = is_ancestor(project, remote_sha, local_sha)
            needs_special_handling = not remote_is_ancestor
            if remote_is_ancestor:
                self._log_background(f"Remote-{branch} ist Vorfahr des lokalen Stands; normaler Push ist moeglich.")
            elif local_is_ancestor:
                self._log_background(f"Remote-{branch} enthaelt zusaetzliche Commits; normaler Push waere nicht moeglich.")
            else:
                self._log_background(f"Lokaler und Remote-{branch} sind auseinanderentwickelt.")
        if needs_special_handling and mode == CONFLICT_SAFE:
            steps.append((["push", "-u", "origin", f"HEAD:{branch_ref}"], 1, f"Push abgebrochen: Der Remote-Branch {branch} enthaelt einen anderen Stand."))
            return fail()
        if needs_special_handling and mode == CONFLICT_INTEGRATE:
            merge_args = ["merge", "--no-edit"]
            if not has_common_base(project, local_sha, remote_sha):
                merge_args.append("--allow-unrelated-histories")
            merge_args.append(remote_ref)
            code, _ = run(merge_args)
            if code != 0:
                run(["merge", "--abort"])
                return fail()
            code, local_sha_output = run(["rev-parse", "HEAD"])
            if code != 0:
                return fail()
            local_sha = local_sha_output.splitlines()[-1].strip()
        if needs_special_handling and mode == CONFLICT_REPLACE and remote_sha:
            push_args = ["push", f"--force-with-lease={branch_ref}:{remote_sha}", "-u", "origin", f"HEAD:{branch_ref}"]
        else:
            push_args = ["push", "-u", "origin", f"HEAD:{branch_ref}"]
        code, _ = run(push_args)
        if code != 0:
            return fail()
        if tag:
            local_tag_exists = ref_exists(project, f"refs/tags/{tag}")
            if local_tag_exists:
                steps.append((["show-ref", "--verify", "--quiet", f"refs/tags/{tag}"], 0, "Lokaler Tag existiert bereits."))
                return self.events.put(("push_done", steps, "partial"))
            code, remote_tag_listing = run(["ls-remote", "--tags", "origin", f"refs/tags/{tag}"])
            if code != 0 or remote_tag_listing.strip():
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
                        self._log(f"Verbindung erfolgreich. {provider} akzeptiert die Repository-URL und deine lokale Anmeldung.")
                    else:
                        self._log(f"Verbindung fehlgeschlagen. Pruefe URL, Berechtigung sowie SSH- oder Windows-Git-Anmeldung fuer {provider}.")
                    self._set_busy(False)
                elif event[0] == "push_done":
                    _, steps, status = event
                    for args, _code, output in steps:
                        self._log(f"$ {display_command(args)}")
                        if output:
                            self._log(output)
                    if status == "success":
                        provider = self.provider_var.get()
                        self._log(f"Fertig: Das Projekt wurde erfolgreich zu {provider} gepusht.")
                        messagebox.showinfo("Push erfolgreich", f"Das Projekt wurde erfolgreich zu {provider} gepusht.")
                    elif status == "partial":
                        self._log("Der Branch wurde gepusht, aber der optionale Tag konnte nicht erstellt oder gepusht werden.")
                        messagebox.showwarning("Push teilweise erfolgreich", "Der Branch wurde gepusht. Beim optionalen Tag ist ein Fehler aufgetreten.")
                    else:
                        self._log("Push fehlgeschlagen. Die Ausgabe oben enthaelt die Git-Fehlermeldung.")
                        messagebox.showerror("Push fehlgeschlagen", "Git konnte den Push nicht abschliessen. Pruefe die Statusausgabe.")
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(100, self._process_events)


if __name__ == "__main__":
    app = GitLabPusher()
    app.mainloop()
