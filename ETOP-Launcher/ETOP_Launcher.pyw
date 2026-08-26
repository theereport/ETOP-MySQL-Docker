from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "ETOP Launcher"
DEFAULT_PROJECT_ROOT = Path(r"D:\ETOP")

FRONTEND_URL = "http://127.0.0.1:5173/"
BACKEND_URL = "http://127.0.0.1:8000/"
API_DOCS_URL = "http://127.0.0.1:8000/docs"
HEALTH_URL = "http://127.0.0.1:8000/health"
OLLAMA_URL = "http://127.0.0.1:11434/api/tags"

# Secondary dev instance (e.g. a second checkout or branch) - not started or
# health-checked by this launcher, just a quick way to open it if it's running.
DEV_FRONTEND_URL = "http://127.0.0.1:5174/"
DEV_API_DOCS_URL = "http://127.0.0.1:8001/docs"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
CREATE_NEW_PROCESS_GROUP = getattr(
    subprocess,
    "CREATE_NEW_PROCESS_GROUP",
    0x00000200,
)


def fetch_json(url: str, timeout: float = 1.5) -> tuple[bool, dict | list | None, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ETOP-Launcher/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")

        if not raw:
            return True, None, "Available"

        try:
            return True, json.loads(raw), "Available"
        except json.JSONDecodeError:
            return True, None, "Available"

    except urllib.error.HTTPError as exc:
        return False, None, f"HTTP {exc.code}"
    except urllib.error.URLError:
        return False, None, "Unavailable"
    except TimeoutError:
        return False, None, "Timed out"
    except Exception as exc:
        return False, None, str(exc)


class ServiceProcess:
    def __init__(self, name: str, log_queue: queue.Queue):
        self.name = name
        self.log_queue = log_queue
        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, command: list[str], cwd: Path) -> None:
        if self.is_running:
            self.log(f"{self.name} is already running.")
            return

        self.log(f"Starting {self.name}...")
        self.log(f"Working directory: {cwd}")
        self.log("Command: " + " ".join(command))

        self.process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )

        self.reader_thread = threading.Thread(
            target=self._read_output,
            name=f"{self.name}-output",
            daemon=True,
        )
        self.reader_thread.start()

    def _read_output(self) -> None:
        process = self.process

        if process is None or process.stdout is None:
            return

        for line in iter(process.stdout.readline, ""):
            cleaned = line.rstrip()
            if cleaned:
                self.log(cleaned)

        exit_code = process.poll()
        self.log(f"{self.name} stopped with exit code {exit_code}.")

    def stop(self) -> None:
        process = self.process

        if process is None or process.poll() is not None:
            self.process = None
            return

        self.log(f"Stopping {self.name}...")

        try:
            subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        except Exception as exc:
            self.log(f"Unable to stop {self.name}: {exc}")
            try:
                process.kill()
            except Exception:
                pass
        finally:
            self.process = None

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put((self.name, f"[{timestamp}] {message}"))


class ETOPLauncher(tk.Tk):
    STATUS_COLORS = {
        "online": "#28c781",
        "warning": "#f6c453",
        "offline": "#ef6b73",
        "checking": "#8796ad",
    }

    def __init__(self) -> None:
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1040x720")
        self.minsize(900, 620)
        self.configure(bg="#080d17")

        self.project_root = tk.StringVar(value=str(DEFAULT_PROJECT_ROOT))
        self.auto_open_browser = tk.BooleanVar(value=True)
        self.auto_start_ollama = tk.BooleanVar(value=False)

        self.log_queue: queue.Queue = queue.Queue()
        self.backend = ServiceProcess("Backend", self.log_queue)
        self.frontend = ServiceProcess("Frontend", self.log_queue)
        self.ollama = ServiceProcess("Ollama", self.log_queue)

        self.status_labels: dict[str, tuple[tk.Label, tk.Label]] = {}
        self.browser_opened = False
        self.is_closing = False

        self._configure_styles()
        self._build_ui()
        self._validate_project_root(show_message=False)

        self.after(100, self._drain_logs)
        self.after(300, self._schedule_health_check)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "ETOP.TButton",
            background="#172235",
            foreground="#e6edf7",
            bordercolor="#263349",
            padding=(12, 8),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "ETOP.TButton",
            background=[("active", "#22314a")],
            foreground=[("disabled", "#5f6f86")],
        )

        style.configure(
            "Primary.TButton",
            background="#6757df",
            foreground="#ffffff",
            bordercolor="#7868ff",
            padding=(14, 9),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#7868ff")],
        )

        style.configure(
            "Danger.TButton",
            background="#3a1c25",
            foreground="#ffadb3",
            bordercolor="#6e2f3e",
            padding=(12, 8),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#522431")],
        )

        style.configure(
            "ETOP.TCheckbutton",
            background="#0f1726",
            foreground="#cbd5e1",
            font=("Segoe UI", 9),
        )

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg="#0c1320", height=74)
        header.pack(fill="x")
        header.pack_propagate(False)

        brand = tk.Frame(header, bg="#0c1320")
        brand.pack(side="left", padx=18, pady=13)

        mark = tk.Label(
            brand,
            text="E",
            bg="#6757df",
            fg="white",
            width=3,
            height=1,
            font=("Segoe UI", 13, "bold"),
        )
        mark.pack(side="left", padx=(0, 10))

        title_frame = tk.Frame(brand, bg="#0c1320")
        title_frame.pack(side="left")

        tk.Label(
            title_frame,
            text="ETOP Launcher",
            bg="#0c1320",
            fg="#f8fafc",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")

        tk.Label(
            title_frame,
            text="Enterprise Tire Operating Platform",
            bg="#0c1320",
            fg="#8796ad",
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        header_actions = tk.Frame(header, bg="#0c1320")
        header_actions.pack(side="right", padx=18)

        ttk.Button(
            header_actions,
            text="Open ETOP",
            style="ETOP.TButton",
            command=lambda: webbrowser.open(FRONTEND_URL),
        ).pack(side="left", padx=4)

        ttk.Button(
            header_actions,
            text="ETOP Dev",
            style="ETOP.TButton",
            command=self._open_dev_instance,
        ).pack(side="left", padx=4)

        ttk.Button(
            header_actions,
            text="API Docs",
            style="ETOP.TButton",
            command=lambda: webbrowser.open(API_DOCS_URL),
        ).pack(side="left", padx=4)

        body = tk.Frame(self, bg="#080d17")
        body.pack(fill="both", expand=True, padx=16, pady=16)

        top = tk.Frame(body, bg="#080d17")
        top.pack(fill="x")

        control_card = self._card(top)
        control_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        status_card = self._card(top)
        status_card.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._build_controls(control_card)
        self._build_status(status_card)

        logs_card = self._card(body)
        logs_card.pack(fill="both", expand=True, pady=(16, 0))
        self._build_logs(logs_card)

    def _card(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent,
            bg="#0f1726",
            highlightbackground="#263349",
            highlightthickness=1,
        )

    def _section_title(self, parent: tk.Widget, title: str, subtitle: str) -> None:
        heading = tk.Frame(parent, bg="#0f1726")
        heading.pack(fill="x", padx=16, pady=(14, 10))

        tk.Label(
            heading,
            text=title,
            bg="#0f1726",
            fg="#f8fafc",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        tk.Label(
            heading,
            text=subtitle,
            bg="#0f1726",
            fg="#8796ad",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(2, 0))

    def _build_controls(self, parent: tk.Frame) -> None:
        self._section_title(
            parent,
            "Platform Controls",
            "Start, stop, and open the local ETOP development environment.",
        )

        path_frame = tk.Frame(parent, bg="#0f1726")
        path_frame.pack(fill="x", padx=16, pady=(0, 12))

        tk.Label(
            path_frame,
            text="Project folder",
            bg="#0f1726",
            fg="#cbd5e1",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")

        entry = tk.Entry(
            path_frame,
            textvariable=self.project_root,
            bg="#080d17",
            fg="#e6edf7",
            insertbackground="#e6edf7",
            relief="flat",
            highlightbackground="#263349",
            highlightcolor="#7868ff",
            highlightthickness=1,
            font=("Consolas", 9),
        )
        entry.pack(fill="x", pady=(6, 0), ipady=7)

        options = tk.Frame(parent, bg="#0f1726")
        options.pack(fill="x", padx=16)

        ttk.Checkbutton(
            options,
            text="Open ETOP when ready",
            variable=self.auto_open_browser,
            style="ETOP.TCheckbutton",
        ).pack(side="left")

        ttk.Checkbutton(
            options,
            text="Start Ollama if unavailable",
            variable=self.auto_start_ollama,
            style="ETOP.TCheckbutton",
        ).pack(side="left", padx=(18, 0))

        actions = tk.Frame(parent, bg="#0f1726")
        actions.pack(fill="x", padx=16, pady=16)

        ttk.Button(
            actions,
            text="Start All",
            style="Primary.TButton",
            command=self.start_all,
        ).pack(side="left", padx=(0, 7))

        ttk.Button(
            actions,
            text="Stop All",
            style="Danger.TButton",
            command=self.stop_all,
        ).pack(side="left", padx=7)

        ttk.Button(
            actions,
            text="Restart",
            style="ETOP.TButton",
            command=self.restart_all,
        ).pack(side="left", padx=7)

        ttk.Button(
            actions,
            text="Check Status",
            style="ETOP.TButton",
            command=self._schedule_health_check,
        ).pack(side="left", padx=7)

    def _build_status(self, parent: tk.Frame) -> None:
        self._section_title(
            parent,
            "Platform Status",
            "Live checks for the ETOP services and dependencies.",
        )

        status_grid = tk.Frame(parent, bg="#0f1726")
        status_grid.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        for row, (key, label) in enumerate(
            [
                ("frontend", "Frontend"),
                ("backend", "Backend API"),
                ("mysql", "MaddenCo / MySQL"),
                ("ollama", "Ollama"),
                ("knowledge", "Knowledge Base"),
            ]
        ):
            dot = tk.Label(
                status_grid,
                text="\u25cf",
                bg="#0f1726",
                fg=self.STATUS_COLORS["checking"],
                font=("Segoe UI", 11),
            )
            dot.grid(row=row, column=0, sticky="w", pady=5)

            tk.Label(
                status_grid,
                text=label,
                bg="#0f1726",
                fg="#dbe4f0",
                font=("Segoe UI", 9, "bold"),
            ).grid(row=row, column=1, sticky="w", padx=(8, 12), pady=5)

            detail = tk.Label(
                status_grid,
                text="Checking...",
                bg="#0f1726",
                fg="#8796ad",
                font=("Segoe UI", 8),
                anchor="e",
            )
            detail.grid(row=row, column=2, sticky="e", pady=5)

            self.status_labels[key] = (dot, detail)

        status_grid.columnconfigure(1, weight=1)
        status_grid.columnconfigure(2, weight=1)

    def _build_logs(self, parent: tk.Frame) -> None:
        heading = tk.Frame(parent, bg="#0f1726")
        heading.pack(fill="x", padx=14, pady=(12, 8))

        tk.Label(
            heading,
            text="Service Logs",
            bg="#0f1726",
            fg="#f8fafc",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")

        ttk.Button(
            heading,
            text="Clear",
            style="ETOP.TButton",
            command=lambda: self.log_text.delete("1.0", "end"),
        ).pack(side="right")

        log_frame = tk.Frame(parent, bg="#080d17")
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")

        self.log_text = tk.Text(
            log_frame,
            bg="#080d17",
            fg="#cbd5e1",
            insertbackground="#e6edf7",
            relief="flat",
            wrap="word",
            font=("Consolas", 9),
            yscrollcommand=scrollbar.set,
        )
        self.log_text.pack(fill="both", expand=True)
        scrollbar.config(command=self.log_text.yview)

        self.log_text.tag_configure("Backend", foreground="#7dd3fc")
        self.log_text.tag_configure("Frontend", foreground="#c4b5fd")
        self.log_text.tag_configure("Ollama", foreground="#86efac")
        self.log_text.tag_configure("Launcher", foreground="#f6c453")

    def project_root_path(self) -> Path:
        return Path(self.project_root.get().strip()).expanduser()

    def _validate_project_root(self, show_message: bool = True) -> bool:
        root = self.project_root_path()
        required = [
            root / "package.json",
            root / "backend" / "main.py",
            root / "backend" / ".venv" / "Scripts" / "python.exe",
        ]
        missing = [str(path) for path in required if not path.exists()]

        if missing:
            if show_message:
                messagebox.showerror(
                    APP_NAME,
                    "The ETOP project folder is missing required files:\n\n"
                    + "\n".join(missing),
                )
            return False

        return True

    def start_all(self) -> None:
        if not self._validate_project_root():
            return

        self.browser_opened = False
        root = self.project_root_path()
        backend_root = root / "backend"

        if self.auto_start_ollama.get():
            self._start_ollama_if_needed()

        if not self.backend.is_running:
            self.backend.start(
                [
                    str(backend_root / ".venv" / "Scripts" / "python.exe"),
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                    "--reload",
                ],
                backend_root,
            )
        else:
            self._launcher_log("Backend process is already managed by the launcher.")

        if not self.frontend.is_running:
            npm_command = shutil.which("npm.cmd") or "npm.cmd"
            self.frontend.start(
                [
                    npm_command,
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                ],
                root,
            )
        else:
            self._launcher_log("Frontend process is already managed by the launcher.")

        self.after(600, self._schedule_health_check)

    def _start_ollama_if_needed(self) -> None:
        available, _, _ = fetch_json(OLLAMA_URL)

        if available:
            self._launcher_log("Ollama is already available.")
            return

        executable = shutil.which("ollama.exe") or shutil.which("ollama")

        if not executable:
            self._launcher_log(
                "Ollama is unavailable and ollama.exe was not found on PATH."
            )
            return

        self.ollama.start([executable, "serve"], self.project_root_path())

    def stop_all(self) -> None:
        self.frontend.stop()
        self.backend.stop()
        self.ollama.stop()
        self.browser_opened = False
        self.after(300, self._schedule_health_check)

    def restart_all(self) -> None:
        self._launcher_log("Restarting ETOP...")
        self.stop_all()
        self.after(900, self.start_all)

    def _open_dev_instance(self) -> None:
        webbrowser.open(DEV_FRONTEND_URL)
        webbrowser.open(DEV_API_DOCS_URL)

    def _launcher_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put(("Launcher", f"[{timestamp}] {message}"))

    def _drain_logs(self) -> None:
        try:
            while True:
                service, message = self.log_queue.get_nowait()
                self.log_text.insert("end", f"[{service}] {message}\n", service)
                self.log_text.see("end")
        except queue.Empty:
            pass

        if not self.is_closing:
            self.after(100, self._drain_logs)

    def _set_status(self, key: str, state: str, detail: str) -> None:
        dot, label = self.status_labels[key]
        dot.config(fg=self.STATUS_COLORS[state])
        label.config(text=detail)

    def _schedule_health_check(self) -> None:
        threading.Thread(
            target=self._run_health_check,
            name="ETOP-health-check",
            daemon=True,
        ).start()

    def _run_health_check(self) -> None:
        checks = {
            "frontend": fetch_json(FRONTEND_URL),
            "backend": fetch_json(HEALTH_URL),
            "ollama": fetch_json(OLLAMA_URL),
        }

        frontend_ok, _, _ = checks["frontend"]
        backend_http_ok, health_data, backend_message = checks["backend"]
        ollama_ok, ollama_data, ollama_message = checks["ollama"]

        backend_ready = bool(
            backend_http_ok
            and isinstance(health_data, dict)
            and health_data.get("backend_ready", True)
        )

        self.after(
            0,
            lambda: self._set_status(
                "frontend",
                "online" if frontend_ok else "offline",
                "Running on port 5173" if frontend_ok else "Not running",
            ),
        )

        self.after(
            0,
            lambda: self._set_status(
                "backend",
                "online" if backend_ready else "offline",
                "Online" if backend_ready else backend_message,
            ),
        )

        mysql_ready = bool(
            backend_ready
            and isinstance(health_data, dict)
            and health_data.get("madden_database_ready")
        )
        mysql_detail = (
            "Connected"
            if mysql_ready
            else (
                "Database connection unavailable"
                if backend_ready
                else "Backend unavailable"
            )
        )
        self.after(
            0,
            lambda: self._set_status(
                "mysql",
                "online" if mysql_ready else (
                    "warning" if backend_ready else "offline"
                ),
                mysql_detail,
            ),
        )

        model_count = 0
        if isinstance(ollama_data, dict):
            models = ollama_data.get("models")
            if isinstance(models, list):
                model_count = len(models)

        self.after(
            0,
            lambda: self._set_status(
                "ollama",
                "online" if ollama_ok else "offline",
                (
                    f"Online \u2022 {model_count} models"
                    if ollama_ok
                    else ollama_message
                ),
            ),
        )

        knowledge_ready = bool(
            backend_ready
            and isinstance(health_data, dict)
            and health_data.get(
                "knowledge_ready",
                health_data.get("knowledge_database_exists", False),
            )
        )
        knowledge_detail = (
            "Online"
            if knowledge_ready
            else (
                "Knowledge database unavailable"
                if backend_ready
                else "Backend unavailable"
            )
        )
        self.after(
            0,
            lambda: self._set_status(
                "knowledge",
                "online" if knowledge_ready else (
                    "warning" if backend_ready else "offline"
                ),
                knowledge_detail,
            ),
        )
    def _on_close(self) -> None:
        managed_running = (
            self.backend.is_running
            or self.frontend.is_running
            or self.ollama.is_running
        )

        if managed_running:
            should_stop = messagebox.askyesno(
                APP_NAME,
                "Stop the ETOP services started by this launcher before closing?",
            )
            if should_stop:
                self.stop_all()

        self.is_closing = True
        self.destroy()


if __name__ == "__main__":
    ETOPLauncher().mainloop()
