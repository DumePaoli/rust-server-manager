#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           🦀  RUST SERVER MANAGER  v1.1                      ║
║   Gérez votre serveur Rust moddé avec Carbon + Tebex         ║
╚══════════════════════════════════════════════════════════════╝
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess
import threading
import os
import sys
import json
import urllib.request
import urllib.error
import zipfile
import shutil
from pathlib import Path
import time
import webbrowser
import re
import tempfile

# ─────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────
APP_VERSION     = "1.1.0"
CONFIG_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rust_manager_config.json")
STEAMCMD_URL    = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
CARBON_API      = "https://api.github.com/repos/CarbonCommunity/Carbon/releases/latest"
RUST_APP_ID     = "258550"

# ── Auto-update ──────────────────────────────
# ⚙️  Remplacez par votre propre dépôt GitHub après avoir créé la release
#     Format : "username/nom-du-repo"  (ex: "dylan/rust-server-manager")
GITHUB_REPO     = ""   # ← À remplir une seule fois

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
class Config:
    DEFAULTS = {
        "install_path":      "",
        "server_hostname":   "Mon Serveur Rust",
        "server_port":       "28015",
        "server_maxplayers": "50",
        "server_seed":       "12345",
        "server_worldsize":  "3000",
        "server_identity":   "myserver",
        "rcon_port":         "28016",
        "rcon_password":     "Changezmoi123",
        "tebex_api_key":     "",
        "grades": [
            {"name": "VIP",     "price": "5€",  "kit": "kit_vip",      "group": "vip"},
            {"name": "VIP+",    "price": "10€", "kit": "kit_vipplus",  "group": "vipplus"},
            {"name": "PREMIUM", "price": "20€", "kit": "kit_premium",  "group": "premium"},
        ]
    }

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


# ─────────────────────────────────────────────
#  SERVER PROCESS
# ─────────────────────────────────────────────
class ServerProcess:
    def __init__(self):
        self.process = None
        self.running = False

    @staticmethod
    def find_rust_exe(base_path: str) -> str | None:
        """Cherche RustDedicated.exe dans base_path et ses sous-dossiers (profondeur illimitée)."""
        if not base_path or not os.path.exists(base_path):
            return None
        # 1. Chemins connus en priorité (rapide)
        candidates = [
            base_path,
            os.path.join(base_path, "steamcmd", "steamapps", "common", "rust_dedicated"),
            os.path.join(base_path, "steamapps", "common", "rust_dedicated"),
            os.path.join(base_path, "rust_dedicated"),
            os.path.join(base_path, "server"),
        ]
        for c in candidates:
            if os.path.exists(os.path.join(c, "RustDedicated.exe")):
                return c
        # 2. Recherche récursive complète
        try:
            for root, dirs, files in os.walk(base_path):
                # Ignorer les dossiers système / steam inutiles
                dirs[:] = [d for d in dirs if d.lower() not in
                           ("__pycache__", "depot_downloader", "package", "logs", "linux")]
                if "RustDedicated.exe" in files:
                    return root
        except PermissionError:
            pass
        return None

    def start(self, cfg: Config, log_cb):
        if self.running:
            log_cb("⚠️  Le serveur est déjà en cours d'exécution.")
            return False

        install_path = cfg.get("install_path", "")
        if not install_path:
            log_cb("❌  Aucun chemin d'installation défini.")
            return False

        # 1. Utiliser l'override manuel si défini
        server_dir = cfg.get("server_dir_override", "").strip()
        if server_dir and os.path.exists(os.path.join(server_dir, "RustDedicated.exe")):
            log_cb(f"ℹ️  Dossier serveur (manuel) : {server_dir}")
        else:
            # 2. Auto-détection
            server_dir = self.find_rust_exe(install_path)
            if not server_dir:
                log_cb(f"❌  RustDedicated.exe introuvable sous : {install_path}")
                log_cb("    → Onglet Installation → 'Dossier serveur' → coller le chemin manuellement.")
                return False
            if server_dir != install_path:
                log_cb(f"ℹ️  Serveur auto-détecté : {server_dir}")

        exe = os.path.join(server_dir, "RustDedicated.exe")

        cmd = [
            exe, "-batchmode",
            f"+server.port",       cfg.get("server_port", "28015"),
            f"+server.hostname",   cfg.get("server_hostname", "Mon Serveur"),
            f"+server.maxplayers", cfg.get("server_maxplayers", "50"),
            f"+server.seed",       cfg.get("server_seed", "12345"),
            f"+server.worldsize",  cfg.get("server_worldsize", "3000"),
            f"+server.identity",   cfg.get("server_identity", "myserver"),
            f"+rcon.port",         cfg.get("rcon_port", "28016"),
            f"+rcon.password",     cfg.get("rcon_password", "password"),
            "+rcon.web", "1",
            "+app.port", "28082",
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=server_dir,
            )
            self.running = True

            def _read():
                for line in self.process.stdout:
                    log_cb(line.rstrip())
                self.running = False
                log_cb("─── Serveur arrêté ───")

            threading.Thread(target=_read, daemon=True).start()
            log_cb(f"✅  Serveur démarré  (PID: {self.process.pid})")
            return True
        except Exception as e:
            log_cb(f"❌  Erreur au démarrage : {e}")
            self.running = False
            return False

    def stop(self, log_cb):
        if not self.process or not self.running:
            log_cb("⚠️  Le serveur n'est pas en cours d'exécution.")
            return
        try:
            self.process.terminate()
            log_cb("⏹  Arrêt en cours…")
            self.process.wait(timeout=30)
        except Exception:
            self.process.kill()
        finally:
            self.running = False
            log_cb("✅  Serveur arrêté.")

    def send_cmd(self, cmd: str, log_cb):
        if not self.process or not self.running:
            log_cb("⚠️  Le serveur n'est pas en cours d'exécution.")
            return
        try:
            self.process.stdin.write(cmd + "\n")
            self.process.stdin.flush()
        except Exception as e:
            log_cb(f"❌  Erreur d'envoi de commande : {e}")


# ─────────────────────────────────────────────
#  HELPERS UI
# ─────────────────────────────────────────────
DARK_BG    = "#12131a"
CARD_BG    = "#1c1e2e"
CARD_BG2   = "#22243a"
ACCENT     = "#4e88ff"
ACCENT2    = "#7c5cfc"
GREEN      = "#00e676"
RED        = "#ff3d3d"
ORANGE     = "#ff9100"
GRAY_TXT   = "#6c6f8e"
SIDEBAR_W  = 220


# ─────────────────────────────────────────────
#  AUTO-UPDATER
# ─────────────────────────────────────────────
class Updater:
    """Vérifie et applique les mises à jour depuis GitHub Releases."""

    @staticmethod
    def _parse_version(v: str) -> tuple:
        """Convertit '1.2.3' en (1, 2, 3) pour comparer."""
        try:
            return tuple(int(x) for x in v.lstrip("v").split("."))
        except Exception:
            return (0, 0, 0)

    @staticmethod
    def check(callback):
        """
        Vérifie en arrière-plan si une mise à jour est disponible.
        callback(latest_version, download_url) si nouvelle version, sinon callback(None, None).
        """
        if not GITHUB_REPO:
            callback(None, None)
            return

        def _do():
            try:
                url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": "RustServerManager"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())

                latest_tag  = data.get("tag_name", "0.0.0")
                latest_ver  = Updater._parse_version(latest_tag)
                current_ver = Updater._parse_version(APP_VERSION)

                if latest_ver > current_ver:
                    # Chercher l'asset .py dans la release
                    dl_url = None
                    for asset in data.get("assets", []):
                        if asset["name"].endswith(".py"):
                            dl_url = asset["browser_download_url"]
                            break
                    # Fallback : URL raw du repo (zipball)
                    if not dl_url:
                        dl_url = data.get("zipball_url", "")
                    callback(latest_tag, dl_url)
                else:
                    callback(None, None)
            except Exception:
                callback(None, None)

        threading.Thread(target=_do, daemon=True).start()

    @staticmethod
    def apply(download_url: str, log_cb, done_cb):
        """
        Télécharge la nouvelle version, remplace le fichier courant et relance l'app.
        log_cb(str) pour afficher la progression.
        done_cb(success: bool) appelé à la fin.
        """
        def _do():
            try:
                current_file = os.path.abspath(__file__)
                backup_file  = current_file + ".backup"

                log_cb("📥  Téléchargement de la mise à jour…")
                req = urllib.request.Request(
                    download_url, headers={"User-Agent": "RustServerManager"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read()

                # Si c'est un .py direct
                if download_url.endswith(".py"):
                    new_content = content
                else:
                    # C'est un zipball GitHub — extraire le .py
                    log_cb("📦  Extraction de l'archive…")
                    tmp_zip = tempfile.mktemp(suffix=".zip")
                    with open(tmp_zip, "wb") as f:
                        f.write(content)
                    new_content = None
                    with zipfile.ZipFile(tmp_zip, "r") as z:
                        for name in z.namelist():
                            if name.endswith("RustServerManager.py"):
                                new_content = z.read(name)
                                break
                    os.remove(tmp_zip)
                    if not new_content:
                        log_cb("❌  Fichier RustServerManager.py introuvable dans l'archive.")
                        done_cb(False)
                        return

                # Sauvegarde de l'ancienne version
                log_cb("💾  Sauvegarde de l'ancienne version…")
                shutil.copy2(current_file, backup_file)

                # Écriture de la nouvelle version
                log_cb("✍️  Application de la mise à jour…")
                with open(current_file, "wb") as f:
                    f.write(new_content)

                log_cb("✅  Mise à jour appliquée ! Redémarrage dans 3 secondes…")
                done_cb(True)

                # Relancer l'application
                time.sleep(3)
                subprocess.Popen([sys.executable, current_file])
                os._exit(0)

            except Exception as e:
                log_cb(f"❌  Erreur lors de la mise à jour : {e}")
                # Restaurer la sauvegarde si elle existe
                if os.path.exists(backup_file):
                    shutil.copy2(backup_file, current_file)
                    log_cb("↩️  Ancienne version restaurée.")
                done_cb(False)

        threading.Thread(target=_do, daemon=True).start()


def card(parent, **kwargs):
    return ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=12, **kwargs)


def section_label(parent, text):
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=GRAY_TXT
    ).pack(anchor="w", padx=20, pady=(16, 4))


def h1(parent, text):
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=24, weight="bold")
    ).pack(anchor="w", padx=30, pady=(28, 6))


def separator(parent):
    ctk.CTkFrame(parent, height=1, fg_color="#2a2d40", corner_radius=0).pack(
        fill="x", padx=20, pady=6
    )


# ─────────────────────────────────────────────
#  APPLICATION
# ─────────────────────────────────────────────
class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self.srv = ServerProcess()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("🦀  Rust Server Manager")
        self.geometry("1160x780")
        self.minsize(900, 620)
        self.configure(fg_color=DARK_BG)

        self._build_sidebar()
        self._build_main()

        # Tabs
        self.tabs = {}
        self._tab_dashboard()
        self._tab_install()
        self._tab_config()
        self._tab_plugins()
        self._tab_tebex()
        self._tab_console()
        self._tab_updates()

        self._show("dashboard")
        self._tick_status()

        # Vérification des mises à jour au démarrage (arrière-plan)
        self.after(2000, self._start_update_check)

    # ══════════════════════════════════════════
    #  SIDEBAR
    # ══════════════════════════════════════════
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=SIDEBAR_W, corner_radius=0, fg_color="#0d0e18")
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # Logo
        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.pack(fill="x", pady=(28, 8))
        ctk.CTkLabel(logo, text="🦀", font=ctk.CTkFont(size=38)).pack()
        ctk.CTkLabel(logo, text="Rust Manager",
                     font=ctk.CTkFont(size=17, weight="bold")).pack()
        ctk.CTkLabel(logo, text=f"v{APP_VERSION}",
                     text_color=GRAY_TXT,
                     font=ctk.CTkFont(size=11)).pack()

        ctk.CTkFrame(sb, height=1, fg_color="#1e2035").pack(fill="x", padx=14, pady=10)

        # Status pill
        pill = ctk.CTkFrame(sb, fg_color="#1a1b2e", corner_radius=20)
        pill.pack(fill="x", padx=14, pady=(0, 10))
        self._status_dot = ctk.CTkLabel(pill, text="⬤", text_color=RED,
                                        font=ctk.CTkFont(size=10))
        self._status_dot.pack(side="left", padx=(12, 4), pady=8)
        self._status_lbl = ctk.CTkLabel(pill, text="Serveur arrêté",
                                        font=ctk.CTkFont(size=12))
        self._status_lbl.pack(side="left")

        ctk.CTkFrame(sb, height=1, fg_color="#1e2035").pack(fill="x", padx=14, pady=(0, 8))

        # Nav
        nav_items = [
            ("🏠", "Tableau de bord",  "dashboard"),
            ("⚙️", "Installation",      "install"),
            ("🔧", "Configuration",     "config"),
            ("🧩", "Plugins",           "plugins"),
            ("🛒", "Boutique Tebex",    "tebex"),
            ("📜", "Console",           "console"),
            ("⬆️", "Mises à jour",      "updates"),
        ]
        self._nav_btns = {}
        for icon, label, key in nav_items:
            btn = ctk.CTkButton(
                sb,
                text=f"  {icon}  {label}",
                anchor="w",
                height=42,
                corner_radius=10,
                fg_color="transparent",
                text_color="#9da3c8",
                hover_color="#1e2035",
                font=ctk.CTkFont(size=13),
                command=lambda k=key: self._show(k),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[key] = btn

        # Bottom buttons
        ctk.CTkFrame(sb, height=1, fg_color="#1e2035").pack(fill="x", padx=14, pady=(12, 8), side="bottom")
        ctk.CTkButton(
            sb, text="🌐  uMod.org", anchor="w",
            height=36, corner_radius=10,
            fg_color="transparent", text_color=GRAY_TXT,
            hover_color="#1e2035",
            command=lambda: webbrowser.open("https://umod.org/games/rust"),
        ).pack(fill="x", padx=10, pady=2, side="bottom")

        # Bannière mise à jour (cachée par défaut)
        self._update_banner = ctk.CTkFrame(sb, fg_color="#1a3a0a", corner_radius=10)
        # (ne pas .pack ici — affiché dynamiquement)
        self._update_version_lbl = ctk.CTkLabel(
            self._update_banner, text="🆕  Mise à jour disponible !",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#a0ff80",
        )
        self._update_version_lbl.pack(pady=(10, 2), padx=10)
        self._update_dl_url = ""
        ctk.CTkButton(
            self._update_banner, text="📥  Mettre à jour", height=32,
            fg_color="#00833b", hover_color="#006b30",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._apply_update,
        ).pack(fill="x", padx=10, pady=(4, 10))

    # ══════════════════════════════════════════
    #  MAIN AREA
    # ══════════════════════════════════════════
    def _build_main(self):
        self._main = ctk.CTkFrame(self, corner_radius=0, fg_color=DARK_BG)
        self._main.pack(side="right", fill="both", expand=True)

    def _show(self, key):
        for k, f in self.tabs.items():
            f.pack_forget()
        for k, b in self._nav_btns.items():
            if k == key:
                b.configure(fg_color="#1e2035", text_color="white")
            else:
                b.configure(fg_color="transparent", text_color="#9da3c8")
        self.tabs[key].pack(fill="both", expand=True)

    # ══════════════════════════════════════════
    #  STATUS TICKER
    # ══════════════════════════════════════════
    def _tick_status(self):
        if self.srv.running:
            self._status_dot.configure(text_color=GREEN)
            self._status_lbl.configure(text="Serveur en ligne")
            if hasattr(self, "_btn_start"):
                self._btn_start.configure(state="disabled")
                self._btn_stop.configure(state="normal")
        else:
            self._status_dot.configure(text_color=RED)
            self._status_lbl.configure(text="Serveur arrêté")
            if hasattr(self, "_btn_start"):
                self._btn_start.configure(state="normal")
                self._btn_stop.configure(state="disabled")
        self.after(1500, self._tick_status)

    # ══════════════════════════════════════════
    #  AUTO-UPDATE
    # ══════════════════════════════════════════
    def _start_update_check(self):
        if not GITHUB_REPO:
            return
        def _on_result(version, url):
            if version and url:
                self.after(0, lambda: self._show_update_banner(version, url))
        Updater.check(_on_result)

    def _show_update_banner(self, version: str, url: str):
        self._update_dl_url = url
        self._update_version_lbl.configure(
            text=f"🆕  v{version} disponible !"
        )
        self._update_banner.pack(fill="x", padx=10, pady=(0, 6), side="bottom", before=self._update_banner.master.winfo_children()[-1] if self._update_banner.master.winfo_children() else None)
        # Notification aussi dans le dashboard
        if hasattr(self, "_dash_update_frame"):
            self._dash_update_frame.pack(fill="x", padx=30, pady=(0, 12))
            self._dash_update_lbl.configure(text=f"🆕  Version {version} disponible — cliquez sur 'Mettre à jour' dans la barre latérale")

    def _apply_update(self):
        if not self._update_dl_url:
            return
        if not messagebox.askyesno(
            "Mise à jour",
            f"Télécharger et installer la nouvelle version ?\n\n"
            f"• L'app redémarrera automatiquement\n"
            f"• Une sauvegarde de l'ancienne version sera créée\n"
            f"• Votre configuration sera conservée",
        ):
            return
        self._show("console")
        self._log_console("━━━ MISE À JOUR ━━━")
        Updater.apply(
            self._update_dl_url,
            log_cb=self._log_console,
            done_cb=lambda ok: self._log_console(
                "✅  Redémarrage…" if ok else "❌  Mise à jour échouée."
            ),
        )

    # ══════════════════════════════════════════
    #  LOG HELPERS
    # ══════════════════════════════════════════
    def _log(self, textbox, text):
        def _do():
            textbox.configure(state="normal")
            textbox.insert("end", text + "\n")
            textbox.see("end")
            textbox.configure(state="disabled")
        self.after(0, _do)

    def _log_console(self, text):
        self._log(self._console_box, text)

    def _log_install(self, text):
        self._log(self._install_log, text)

    def _set_progress(self, val):
        self.after(0, lambda: self._install_bar.set(val))

    # ══════════════════════════════════════════
    #  TAB: DASHBOARD
    # ══════════════════════════════════════════
    def _tab_dashboard(self):
        frame = ctk.CTkFrame(self._main, fg_color="transparent")
        self.tabs["dashboard"] = frame

        h1(frame, "Tableau de bord")

        # ── Bannière mise à jour (cachée par défaut, activée si update dispo) ──
        self._dash_update_frame = ctk.CTkFrame(frame, fg_color="#1a3a0a", corner_radius=10)
        # ne pas pack ici
        self._dash_update_lbl = ctk.CTkLabel(
            self._dash_update_frame, text="",
            text_color="#a0ff80", font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._dash_update_lbl.pack(side="left", padx=20, pady=12)
        ctk.CTkButton(
            self._dash_update_frame, text="📥 Mettre à jour", height=34, width=150,
            fg_color="#00833b", hover_color="#006b30",
            command=self._apply_update,
        ).pack(side="right", padx=20, pady=8)

        # ── Metric cards ──
        metrics = ctk.CTkFrame(frame, fg_color="transparent")
        metrics.pack(fill="x", padx=30, pady=(0, 16))
        metrics.columnconfigure((0, 1, 2, 3), weight=1)

        self._metric_status = self._make_metric(metrics, "Statut",    "Arrêté", RED,    0)
        self._metric_port   = self._make_metric(metrics, "Port",      self.cfg.get("server_port", "28015"), ACCENT, 1)
        self._metric_seed   = self._make_metric(metrics, "Seed",      self.cfg.get("server_seed", "12345"), ACCENT2, 2)
        self._metric_max    = self._make_metric(metrics, "Max joueurs",self.cfg.get("server_maxplayers","50"), ORANGE, 3)

        # ── Action buttons ──
        btn_bar = ctk.CTkFrame(frame, fg_color="transparent")
        btn_bar.pack(fill="x", padx=30, pady=(0, 20))

        self._btn_start = ctk.CTkButton(
            btn_bar, text="▶  Démarrer", width=160, height=48,
            fg_color="#00833b", hover_color="#006b30",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_server,
        )
        self._btn_start.pack(side="left", padx=(0, 8))

        self._btn_stop = ctk.CTkButton(
            btn_bar, text="⬛  Arrêter", width=160, height=48,
            fg_color="#8b0000", hover_color="#6e0000",
            font=ctk.CTkFont(size=15, weight="bold"),
            state="disabled",
            command=self._stop_server,
        )
        self._btn_stop.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_bar, text="🔄  Redémarrer", width=150, height=48,
            fg_color="#2a2d4a", hover_color="#1e2035",
            font=ctk.CTkFont(size=14),
            command=self._restart_server,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_bar, text="📂  Dossier", width=120, height=48,
            fg_color="transparent", border_width=1, border_color="#2a2d4a",
            font=ctk.CTkFont(size=13),
            command=self._open_server_folder,
        ).pack(side="left")

        # ── Quick start guide ──
        guide = card(frame)
        guide.pack(fill="x", padx=30, pady=(0, 20))
        section_label(guide, "  📋  DÉMARRAGE RAPIDE")

        steps = [
            ("1", "Aller dans Installation → installer SteamCMD, puis le serveur Rust, puis Carbon"),
            ("2", "Configurer le serveur dans l'onglet Configuration puis sauvegarder"),
            ("3", "Installer les plugins Kits et Permissions (onglet Plugins → uMod)"),
            ("4", "Configurer Tebex : créer les grades et relier les kits"),
            ("5", "Appuyer sur Démarrer ici et profiter ! 🎉"),
        ]
        for num, text in steps:
            row = ctk.CTkFrame(guide, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=num, width=26, height=26,
                         fg_color=ACCENT, corner_radius=13,
                         font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(4, 10))
            ctk.CTkLabel(row, text=text, font=ctk.CTkFont(size=12), anchor="w").pack(side="left")
        ctk.CTkFrame(guide, height=12, fg_color="transparent").pack()

    def _make_metric(self, parent, title, value, color, col):
        c = card(parent)
        c.grid(row=0, column=col, padx=5, sticky="ew")
        ctk.CTkLabel(c, text=title, text_color=GRAY_TXT,
                     font=ctk.CTkFont(size=11)).pack(pady=(14, 2))
        lbl = ctk.CTkLabel(c, text=str(value), text_color=color,
                            font=ctk.CTkFont(size=20, weight="bold"))
        lbl.pack(pady=(0, 14))
        return lbl

    # ══════════════════════════════════════════
    #  TAB: INSTALLATION
    # ══════════════════════════════════════════
    def _tab_install(self):
        frame = ctk.CTkScrollableFrame(self._main, fg_color="transparent",
                                       scrollbar_button_color="#1e2035")
        self.tabs["install"] = frame
        h1(frame, "Installation")

        # ── Install path ──
        path_card = card(frame)
        path_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(path_card, "  📁  DOSSIERS")

        # — Dossier racine (pour SteamCMD + installation)
        ctk.CTkLabel(path_card, text="Dossier racine  (SteamCMD s'y installera)",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16)
        row = ctk.CTkFrame(path_card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(2, 8))
        self._path_var = tk.StringVar(value=self.cfg.get("install_path", ""))
        ctk.CTkEntry(row, textvariable=self._path_var, height=38,
                     placeholder_text="Ex: C:\\RustServer  (sans espace de préférence)",
                     font=ctk.CTkFont(size=12)).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="Parcourir", width=100, height=38,
                      command=self._browse_path).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="💾 Sauver", width=90, height=38,
                      command=self._save_path).pack(side="left")

        # — Dossier serveur (override manuel si SteamCMD a installé ailleurs)
        ctk.CTkLabel(path_card,
                     text="Dossier serveur  (où se trouve RustDedicated.exe — à remplir si auto-détection échoue)",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16)
        row2 = ctk.CTkFrame(path_card, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(2, 14))
        self._srv_dir_var = tk.StringVar(value=self.cfg.get("server_dir_override", ""))
        ctk.CTkEntry(row2, textvariable=self._srv_dir_var, height=38,
                     placeholder_text="Ex: C:\\RustServer\\steamcmd\\steamapps\\common\\rust_dedicated",
                     font=ctk.CTkFont(size=12)).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row2, text="Parcourir", width=100, height=38,
                      command=self._browse_srv_dir).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row2, text="🔍 Détecter", width=100, height=38,
                      fg_color="#2a3a1a", hover_color="#3a5a1a",
                      command=self._auto_detect_server).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row2, text="💾 Sauver", width=90, height=38,
                      command=self._save_srv_dir).pack(side="left")

        # ── Log + progress ──
        self._install_log = ctk.CTkTextbox(
            frame, height=130,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color="#0a0b10", text_color="#c8ffc8",
        )
        self._install_log.pack(fill="x", padx=30, pady=(0, 6))
        self._install_log.configure(state="disabled")

        self._install_bar = ctk.CTkProgressBar(frame, height=8,
                                               progress_color=ACCENT)
        self._install_bar.pack(fill="x", padx=30, pady=(0, 14))
        self._install_bar.set(0)

        # ── Steps ──
        steps_data = [
            (
                "1", "SteamCMD", ACCENT,
                "Outil officiel Valve pour télécharger les serveurs de jeu. Requis pour installer Rust.",
                "Installer SteamCMD", self._install_steamcmd,
            ),
            (
                "2", "Serveur Rust Dédié", ACCENT2,
                "Télécharge le serveur dédié Rust (~10 Go). Nécessite SteamCMD installé au préalable.",
                "Installer Rust", self._install_rust,
            ),
            (
                "3", "Carbon Framework", "#ff8c00",
                "Framework de mods haute performance pour Rust. Remplace Oxide avec de meilleures performances.",
                "Installer Carbon", self._install_carbon,
            ),
        ]

        for num, title, color, desc, btn_txt, cmd in steps_data:
            c = card(frame)
            c.pack(fill="x", padx=30, pady=5)
            inner = ctk.CTkFrame(c, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=14)

            badge = ctk.CTkLabel(inner, text=num, width=32, height=32,
                                  fg_color=color, corner_radius=16,
                                  font=ctk.CTkFont(size=13, weight="bold"))
            badge.pack(side="left", padx=(0, 14))

            info = ctk.CTkFrame(inner, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(info, text=title, font=ctk.CTkFont(size=14, weight="bold"),
                         anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=desc, text_color=GRAY_TXT,
                         font=ctk.CTkFont(size=11), anchor="w",
                         wraplength=560).pack(anchor="w")

            ctk.CTkButton(inner, text=btn_txt, height=36, width=160,
                          command=cmd).pack(side="right")

        # ── Note ──
        note = card(frame)
        note.pack(fill="x", padx=30, pady=(8, 20))
        ctk.CTkLabel(
            note,
            text="💡  Conseil : Choisissez un SSD avec au moins 15 Go libres. "
                 "Le téléchargement du serveur Rust prend plusieurs minutes selon votre connexion.",
            text_color=GRAY_TXT, font=ctk.CTkFont(size=12),
            wraplength=720, justify="left",
        ).pack(padx=20, pady=14, anchor="w")

    # ══════════════════════════════════════════
    #  TAB: CONFIG
    # ══════════════════════════════════════════
    def _tab_config(self):
        frame = ctk.CTkScrollableFrame(self._main, fg_color="transparent",
                                       scrollbar_button_color="#1e2035")
        self.tabs["config"] = frame
        h1(frame, "Configuration du serveur")

        self._cfg_vars = {}

        sections = [
            ("🌐  Serveur", [
                ("server_hostname",   "Nom du serveur",          "Mon Serveur Rust"),
                ("server_port",       "Port (UDP)",              "28015"),
                ("server_maxplayers", "Nombre max de joueurs",   "50"),
                ("server_identity",   "Identité (dossier save)", "myserver"),
            ]),
            ("🗺️  Carte", [
                ("server_seed",      "Seed de la carte",    "12345"),
                ("server_worldsize", "Taille du monde (m)", "3000"),
            ]),
            ("🔐  RCON (administration à distance)", [
                ("rcon_port",     "Port RCON",       "28016"),
                ("rcon_password", "Mot de passe RCON", "ChangezmoBien!"),
            ]),
        ]

        for sec_title, fields in sections:
            c = card(frame)
            c.pack(fill="x", padx=30, pady=8)
            section_label(c, f"  {sec_title}")

            for key, label, placeholder in fields:
                row = ctk.CTkFrame(c, fg_color="transparent")
                row.pack(fill="x", padx=16, pady=4)
                ctk.CTkLabel(row, text=label, width=220, anchor="w",
                             font=ctk.CTkFont(size=12)).pack(side="left")
                var = tk.StringVar(value=self.cfg.get(key, placeholder))
                is_pw = "password" in key.lower() or "password" in label.lower()
                ctk.CTkEntry(row, textvariable=var, height=36,
                             placeholder_text=placeholder,
                             show="*" if is_pw else "",
                             font=ctk.CTkFont(size=12)).pack(side="left", fill="x", expand=True)
                self._cfg_vars[key] = var

            ctk.CTkFrame(c, height=10, fg_color="transparent").pack()

        ctk.CTkButton(
            frame,
            text="💾  Sauvegarder la configuration",
            height=46,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color="#3a6fd4",
            command=self._save_config,
        ).pack(fill="x", padx=30, pady=(8, 30))

    # ══════════════════════════════════════════
    #  TAB: PLUGINS
    # ══════════════════════════════════════════
    def _tab_plugins(self):
        frame = ctk.CTkScrollableFrame(self._main, fg_color="transparent",
                                       scrollbar_button_color="#1e2035")
        self.tabs["plugins"] = frame
        h1(frame, "Gestion des plugins Carbon")

        # ── Barre d'actions ──
        act = ctk.CTkFrame(frame, fg_color="transparent")
        act.pack(fill="x", padx=30, pady=(0, 10))
        ctk.CTkButton(act, text="📂 Ouvrir dossier plugins", height=36,
                      command=self._open_plugins_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(act, text="🔄 Actualiser la liste", height=36,
                      command=self._refresh_plugins).pack(side="left")

        # ── Log de téléchargement ──
        self._plugin_log = ctk.CTkTextbox(
            frame, height=90,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color="#0a0b10", text_color="#c8ffc8",
        )
        self._plugin_log.pack(fill="x", padx=30, pady=(0, 10))
        self._plugin_log.configure(state="disabled")
        self._log_plugin("ℹ️  Cliquez sur 'Installer' pour télécharger un plugin directement dans votre serveur.")

        # ── Recherche / Installation par slug ──
        search_card = card(frame)
        search_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(search_card, "  🔎  INSTALLER PAR NOM (uMod slug)")
        ctk.CTkLabel(search_card,
                     text="Entrez le nom exact du plugin tel qu'il apparaît dans l'URL uMod  (ex: kits, clans, backpacks)",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16)
        search_row = ctk.CTkFrame(search_card, fg_color="transparent")
        search_row.pack(fill="x", padx=16, pady=(6, 14))
        self._plugin_slug_var = tk.StringVar()
        ctk.CTkEntry(search_row, textvariable=self._plugin_slug_var, height=38,
                     placeholder_text="Ex:  kits   ou   clans   ou   economics",
                     font=ctk.CTkFont(size=13)).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(search_row, text="📥  Installer", height=38, width=130,
                      fg_color="#00833b", hover_color="#006b30",
                      command=lambda: self._install_plugin(
                          self._plugin_slug_var.get().strip().lower(), None
                      )).pack(side="left")

        # ── Plugins installés ──
        inst_card = card(frame)
        inst_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(inst_card, "  📦  PLUGINS INSTALLÉS")
        self._plugin_list = ctk.CTkFrame(inst_card, fg_color="transparent")
        self._plugin_list.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(self._plugin_list,
                     text="Cliquez sur 'Actualiser la liste' pour voir les plugins installés.",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=12)).pack(pady=8)

        # ── Encart permissions Carbon intégrées ──
        perm_card = ctk.CTkFrame(frame, fg_color="#0f2218", corner_radius=12)
        perm_card.pack(fill="x", padx=30, pady=(0, 12))
        ctk.CTkLabel(perm_card,
                     text="💡  Carbon gère les permissions nativement — aucun plugin requis",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#7dffa0").pack(anchor="w", padx=20, pady=(14, 4))
        ctk.CTkLabel(perm_card,
                     text="Utilisez ces commandes dans la Console (onglet Console) ou via RCON :",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)

        cmds = [
            ("Ajouter un joueur à un groupe",       "oxide.usergroup add  <steam64>  <groupe>"),
            ("Retirer un joueur d'un groupe",        "oxide.usergroup remove  <steam64>  <groupe>"),
            ("Donner une permission à un groupe",    "oxide.grant group  <groupe>  <permission>"),
            ("Donner une permission à un joueur",    "oxide.grant user  <steam64>  <permission>"),
            ("Voir les groupes d'un joueur",         "oxide.show user  <steam64>"),
            ("Lister tous les groupes",              "oxide.show groups"),
        ]
        for label, cmd in cmds:
            r = ctk.CTkFrame(perm_card, fg_color="transparent")
            r.pack(fill="x", padx=20, pady=1)
            ctk.CTkLabel(r, text=label, width=260, anchor="w",
                         text_color=GRAY_TXT, font=ctk.CTkFont(size=11)).pack(side="left")
            ctk.CTkLabel(r, text=cmd, anchor="w",
                         text_color="#a0ffc0",
                         font=ctk.CTkFont(family="Courier New", size=11)).pack(side="left")
        ctk.CTkFrame(perm_card, height=12, fg_color="transparent").pack()

        # ── Plugins recommandés ──
        rec_card = card(frame)
        rec_card.pack(fill="x", padx=30, pady=(0, 24))
        section_label(rec_card, "  ⭐  PLUGINS RECOMMANDÉS  —  Installation en 1 clic")

        # (nom, slug uMod, description, badge, couleur badge)
        recommended = [
            ("Kits",                "kits",                "Kits pour vos grades VIP — essentiel pour votre boutique",   "🎁 Essentiel",  GREEN),
            ("Vanish",              "vanish",              "Rend les admins invisibles — essentiel pour modérer",       "🔐 Admin",      GREEN),
            ("Economics",           "economics",           "Monnaie virtuelle in-game (utilisée par d'autres plugins)",   "💰 Utile",      ACCENT),
            ("Backpacks",           "backpacks",           "Sacs à dos extra — parfait comme avantage VIP",              "🎒 Recommandé", ACCENT),
            ("Friends",             "friends",             "Système d'amis (partage de portes, autorisation TC…)",       "👥 Recommandé", ACCENT),
            ("Clans",               "clans",               "Création et gestion de clans",                               "⚔️ Recommandé", ACCENT),
            ("NoEscape",            "no-escape",           "Bloque tp/home/kit pendant ou après un combat",              "🛡️ Recommandé", ACCENT),
            ("VoteDay",             "voteday",             "Vote des joueurs pour passer en journée",                    "☀️ Optionnel",  GRAY_TXT),
            ("GatherManager",       "gather-manager",      "Multiplie les ressources récoltées (x2, x3…)",               "⛏️ Populaire",  ORANGE),
            ("Teleportation",       "teleportation",       "Commandes /home, /tp, /tpr pour les joueurs",                "🏠 Populaire",  ORANGE),
        ]

        self._plugin_btn_refs = {}  # Pour mettre à jour le bouton après install

        for name, slug, desc, badge, badge_color in recommended:
            row = ctk.CTkFrame(rec_card, fg_color=CARD_BG2, corner_radius=8)
            row.pack(fill="x", padx=16, pady=3)

            # Indicateur de statut (⬤ = installé, ○ = non installé)
            status_lbl = ctk.CTkLabel(row, text="○", text_color=GRAY_TXT,
                                      font=ctk.CTkFont(size=14), width=22)
            status_lbl.pack(side="left", padx=(8, 4), pady=8)

            ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=13, weight="bold"),
                         width=165, anchor="w").pack(side="left", padx=(0, 4), pady=10)
            ctk.CTkLabel(row, text=desc, text_color=GRAY_TXT,
                         font=ctk.CTkFont(size=11), anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=badge, text_color=badge_color,
                         font=ctk.CTkFont(size=11), width=110).pack(side="right", padx=8)

            btn = ctk.CTkButton(
                row, text="📥 Installer", width=110, height=30,
                fg_color="#00833b", hover_color="#006b30",
                font=ctk.CTkFont(size=12),
                command=lambda s=slug, n=name, b=status_lbl: self._install_plugin(s, n, b),
            )
            btn.pack(side="right", padx=8, pady=6)
            self._plugin_btn_refs[slug] = (btn, status_lbl)

        ctk.CTkFrame(rec_card, height=8, fg_color="transparent").pack()

        # Vérifier quels plugins sont déjà installés (après rendu)
        self.after(200, self._check_installed_status)

    # ══════════════════════════════════════════
    #  TAB: TEBEX
    # ══════════════════════════════════════════
    def _tab_tebex(self):
        frame = ctk.CTkScrollableFrame(self._main, fg_color="transparent",
                                       scrollbar_button_color="#1e2035")
        self.tabs["tebex"] = frame
        h1(frame, "Boutique Tebex")
        ctk.CTkLabel(frame, text="Configurez votre boutique pour vendre des grades à vos joueurs",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=30, pady=(0, 16))

        # ── Banner ──
        banner = ctk.CTkFrame(frame, fg_color="#0f2744", corner_radius=12)
        banner.pack(fill="x", padx=30, pady=(0, 12))
        ctk.CTkLabel(
            banner,
            text="💡  Tebex est la plateforme n°1 pour les boutiques de serveurs de jeu. "
                 "Paiements sécurisés, intégration Rust native, tableau de bord complet.",
            text_color="#7db8f7", font=ctk.CTkFont(size=12), wraplength=680, justify="left",
        ).pack(side="left", padx=20, pady=14)
        ctk.CTkButton(
            banner, text="Créer un compte →", height=36, width=160,
            fg_color=ACCENT, hover_color="#3a6fd4",
            command=lambda: webbrowser.open("https://www.tebex.io/"),
        ).pack(side="right", padx=16, pady=10)

        # ── API Key ──
        api_card = card(frame)
        api_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(api_card, "  🔑  CLÉ API TEBEX")

        api_row = ctk.CTkFrame(api_card, fg_color="transparent")
        api_row.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(api_row, text="Clé secrète :", width=120, anchor="w").pack(side="left")
        self._tebex_key = tk.StringVar(value=self.cfg.get("tebex_api_key", ""))
        ctk.CTkEntry(api_row, textvariable=self._tebex_key, height=36, show="*",
                     placeholder_text="Tebex Dashboard → Game Servers → votre serveur → API Keys",
                     font=ctk.CTkFont(size=12)).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(api_row, text="💾 Sauver", width=90, height=36,
                      command=self._save_tebex_key).pack(side="left")

        ctk.CTkLabel(api_card, text="Trouvez votre clé sur : Tebex Dashboard → Game Servers → votre serveur → API Keys",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0, 12))

        # ── Plugin Tebex ──
        plug_card = card(frame)
        plug_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(plug_card, "  🔌  PLUGIN TEBEX POUR CARBON")
        ctk.CTkLabel(
            plug_card,
            text="Téléchargez le plugin Tebex officiel et placez-le dans votre dossier carbon/plugins/",
            text_color=GRAY_TXT, font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=16)

        btns = ctk.CTkFrame(plug_card, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(btns, text="📥 Plugin Tebex pour Rust", height=36,
                      command=lambda: webbrowser.open(
                          "https://docs.tebex.io/store/integrations/rust")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="📚 Documentation complète", height=36,
                      fg_color="transparent", border_width=1, border_color="#2a2d4a",
                      command=lambda: webbrowser.open("https://docs.tebex.io")).pack(side="left")

        ctk.CTkFrame(plug_card, height=6, fg_color="transparent").pack()

        # ── Grades / Kits ──
        grades_card = card(frame)
        grades_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(grades_card, "  🎖️  GRADES ET KITS CONFIGURÉS")
        ctk.CTkLabel(
            grades_card,
            text="Pour chaque grade, ajoutez ces commandes dans Tebex Dashboard → Packages → Commands",
            text_color=GRAY_TXT, font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=16, pady=(0, 8))

        # Header
        hdr = ctk.CTkFrame(grades_card, fg_color="#0d0e18", corner_radius=6)
        hdr.pack(fill="x", padx=16, pady=(0, 4))
        for txt, w in [("Grade", 90), ("Prix", 65), ("Groupe", 100), ("Kit", 130), ("Commande Tebex (à copier)", 0)]:
            ctk.CTkLabel(hdr, text=txt, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=GRAY_TXT, width=w, anchor="w").pack(side="left", padx=8, pady=7)

        grades = self.cfg.get("grades", [])
        for g in grades:
            grp  = g.get("group", g["name"].lower())
            kit  = g.get("kit", f"kit_{g['name'].lower()}")
            cmd1 = f"oxide.usergroup add {{player.id}} {grp}"
            cmd2 = f"kits.give {{player.name}} {kit}"
            full_cmd = f"{cmd1}  |  {cmd2}"

            gr = ctk.CTkFrame(grades_card, fg_color=CARD_BG2, corner_radius=8)
            gr.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(gr, text=g["name"], font=ctk.CTkFont(size=12, weight="bold"),
                         width=90, anchor="w").pack(side="left", padx=8, pady=9)
            ctk.CTkLabel(gr, text=g.get("price", "?"), text_color=GREEN,
                         width=65, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(gr, text=grp, font=ctk.CTkFont(family="Courier New", size=11),
                         width=100, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(gr, text=kit, font=ctk.CTkFont(family="Courier New", size=11),
                         width=130, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(gr, text=full_cmd,
                         font=ctk.CTkFont(family="Courier New", size=10),
                         text_color="#8888bb", anchor="w").pack(side="left", padx=4, fill="x", expand=True)

        ctk.CTkFrame(grades_card, height=10, fg_color="transparent").pack()

        # ── Guide ──
        guide_card = card(frame)
        guide_card.pack(fill="x", padx=30, pady=(0, 24))
        section_label(guide_card, "  📖  GUIDE DE CONFIGURATION TEBEX")

        steps_tebex = [
            "Créez un compte Tebex et ajoutez votre serveur Rust (Game Servers → Add Server)",
            "Copiez votre clé API secrète et collez-la dans le champ ci-dessus",
            "Téléchargez le plugin Tebex et placez-le dans carbon/plugins/",
            "Créez vos packages (VIP, VIP+, PREMIUM) dans Tebex Dashboard → Packages",
            "Dans chaque package → Commands → On Purchase, ajoutez la commande correspondante",
            "Exemple VIP :  oxide.usergroup add {player.id} vip  puis  kits.give {player.name} kit_vip",
            "Testez un achat en mode sandbox avant de mettre en production",
        ]
        for i, s in enumerate(steps_tebex, 1):
            r = ctk.CTkFrame(guide_card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(r, text=str(i), width=24, height=24, fg_color=ACCENT2,
                         corner_radius=12, font=ctk.CTkFont(size=10, weight="bold")).pack(side="left", padx=(4, 10))
            ctk.CTkLabel(r, text=s, font=ctk.CTkFont(size=12), anchor="w",
                         wraplength=680, justify="left").pack(side="left")
        ctk.CTkFrame(guide_card, height=12, fg_color="transparent").pack()

    # ══════════════════════════════════════════
    #  TAB: CONSOLE
    # ══════════════════════════════════════════
    def _tab_console(self):
        frame = ctk.CTkFrame(self._main, fg_color="transparent")
        self.tabs["console"] = frame

        # Header
        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x", padx=30, pady=(24, 8))
        h1(hdr, "Console serveur")
        ctk.CTkButton(hdr, text="🗑  Effacer", width=100, height=32,
                      fg_color="transparent", border_width=1, border_color="#2a2d4a",
                      command=self._clear_console).pack(side="right")

        # Console box
        self._console_box = ctk.CTkTextbox(
            frame,
            font=ctk.CTkFont(family="Courier New", size=12),
            fg_color="#080810",
            text_color="#00e676",
            corner_radius=8,
        )
        self._console_box.pack(fill="both", expand=True, padx=30, pady=(0, 8))
        self._console_box.configure(state="disabled")
        self._log_console("🦀  Rust Server Manager - Console prête.")
        self._log_console("    Démarrez le serveur depuis le Tableau de bord pour voir les logs.")
        self._log_console("")

        # Command input
        cmd_row = ctk.CTkFrame(frame, fg_color="transparent")
        cmd_row.pack(fill="x", padx=30, pady=(0, 20))
        ctk.CTkLabel(cmd_row, text=">", font=ctk.CTkFont(family="Courier New", size=18),
                     text_color=GREEN).pack(side="left", padx=(0, 8))
        self._cmd_var = tk.StringVar()
        cmd_entry = ctk.CTkEntry(
            cmd_row, textvariable=self._cmd_var, height=40,
            placeholder_text="Entrez une commande serveur… (Ex: say Bonjour !)",
            font=ctk.CTkFont(family="Courier New", size=12),
        )
        cmd_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        cmd_entry.bind("<Return>", lambda _: self._send_command())
        ctk.CTkButton(cmd_row, text="Envoyer", width=100, height=40,
                      command=self._send_command).pack(side="left")

    # ══════════════════════════════════════════
    #  ACTIONS — Serveur
    # ══════════════════════════════════════════
    def _start_server(self):
        self._show("console")
        threading.Thread(
            target=lambda: self.srv.start(self.cfg, self._log_console),
            daemon=True,
        ).start()

    def _stop_server(self):
        threading.Thread(
            target=lambda: self.srv.stop(self._log_console),
            daemon=True,
        ).start()

    def _restart_server(self):
        def _do():
            if self.srv.running:
                self.srv.stop(self._log_console)
                time.sleep(3)
            self.srv.start(self.cfg, self._log_console)
        self._show("console")
        threading.Thread(target=_do, daemon=True).start()

    def _send_command(self):
        cmd = self._cmd_var.get().strip()
        if not cmd:
            return
        self._log_console(f"> {cmd}")
        self._cmd_var.set("")
        self.srv.send_cmd(cmd, self._log_console)

    def _clear_console(self):
        self._console_box.configure(state="normal")
        self._console_box.delete("1.0", "end")
        self._console_box.configure(state="disabled")

    def _open_server_folder(self):
        p = self.cfg.get("install_path", "")
        if p and os.path.exists(p):
            os.startfile(p)
        else:
            messagebox.showwarning("Attention", "Configurez d'abord le chemin d'installation.")

    def _open_plugins_folder(self):
        plugins = self._get_plugins_dir()
        if plugins:
            os.startfile(plugins)
        else:
            messagebox.showwarning("Introuvable",
                "Dossier carbon/plugins introuvable.\n\n"
                "Assurez-vous d'avoir installé Carbon et défini\n"
                "le dossier serveur dans l'onglet Installation.")

    # ══════════════════════════════════════════
    #  ACTIONS — Config
    # ══════════════════════════════════════════
    def _browse_path(self):
        p = filedialog.askdirectory(title="Dossier d'installation du serveur Rust")
        if p:
            self._path_var.set(p.replace("/", "\\"))

    def _save_path(self):
        p = self._path_var.get().strip()
        if not p:
            messagebox.showwarning("Attention", "Entrez un chemin valide.")
            return
        os.makedirs(p, exist_ok=True)
        self.cfg.set("install_path", p)
        self.cfg.save()
        self._log_install(f"✅  Chemin racine sauvegardé : {p}")
        messagebox.showinfo("Sauvegardé", f"Chemin d'installation défini :\n{p}")

    def _browse_srv_dir(self):
        p = filedialog.askdirectory(title="Dossier contenant RustDedicated.exe")
        if p:
            self._srv_dir_var.set(p.replace("/", "\\"))

    def _save_srv_dir(self):
        p = self._srv_dir_var.get().strip()
        if not p:
            messagebox.showwarning("Attention", "Entrez un chemin valide.")
            return
        exe = os.path.join(p, "RustDedicated.exe")
        if not os.path.exists(exe):
            if not messagebox.askyesno("Introuvable",
                    f"RustDedicated.exe non trouvé dans :\n{p}\n\nSauvegarder quand même ?"):
                return
        self.cfg.set("server_dir_override", p)
        self.cfg.save()
        self._log_install(f"✅  Dossier serveur sauvegardé : {p}")
        messagebox.showinfo("Sauvegardé", f"Dossier serveur :\n{p}")

    def _auto_detect_server(self):
        base = self.cfg.get("install_path", "")
        if not base:
            messagebox.showwarning("Attention", "Définissez d'abord le dossier racine.")
            return
        self._log_install(f"🔍  Recherche de RustDedicated.exe dans {base}…")
        found = ServerProcess.find_rust_exe(base)
        if found:
            self._srv_dir_var.set(found)
            self.cfg.set("server_dir_override", found)
            self.cfg.save()
            self._log_install(f"✅  Serveur trouvé : {found}")
            messagebox.showinfo("Trouvé !", f"RustDedicated.exe détecté dans :\n{found}")
        else:
            self._log_install("❌  RustDedicated.exe introuvable. Installez le serveur d'abord.")
            messagebox.showwarning("Introuvable",
                "RustDedicated.exe non trouvé.\nInstallez le serveur (étape 2) ou entrez le chemin manuellement.")

    def _save_config(self):
        for key, var in self._cfg_vars.items():
            self.cfg.set(key, var.get())
        self.cfg.save()
        # Update dashboard metrics
        self._metric_port.configure(text=self.cfg.get("server_port", "28015"))
        self._metric_seed.configure(text=self.cfg.get("server_seed", "12345"))
        self._metric_max.configure(text=self.cfg.get("server_maxplayers", "50"))
        # Write startup .bat
        self._write_startup_bat()
        messagebox.showinfo("Sauvegardé", "Configuration sauvegardée !\n\nUn fichier start_server.bat a été généré dans votre dossier d'installation.")

    def _write_startup_bat(self):
        """Génère un start_server.bat dans le dossier d'installation."""
        install_path = self.cfg.get("install_path", "")
        if not install_path:
            return
        bat_path = os.path.join(install_path, "start_server.bat")
        content = f"""@echo off
title Rust Server - {self.cfg.get("server_hostname", "Mon Serveur")}
:start
RustDedicated.exe -batchmode ^
  +server.port {self.cfg.get("server_port", "28015")} ^
  +server.hostname "{self.cfg.get("server_hostname", "Mon Serveur Rust")}" ^
  +server.maxplayers {self.cfg.get("server_maxplayers", "50")} ^
  +server.seed {self.cfg.get("server_seed", "12345")} ^
  +server.worldsize {self.cfg.get("server_worldsize", "3000")} ^
  +server.identity {self.cfg.get("server_identity", "myserver")} ^
  +rcon.port {self.cfg.get("rcon_port", "28016")} ^
  +rcon.password "{self.cfg.get("rcon_password", "password")}" ^
  +rcon.web 1 ^
  +app.port 28082
echo Serveur arrete. Redemarrage dans 5 secondes...
timeout /t 5
goto start
"""
        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

    def _save_tebex_key(self):
        self.cfg.set("tebex_api_key", self._tebex_key.get())
        self.cfg.save()
        messagebox.showinfo("Sauvegardé", "Clé API Tebex sauvegardée !")

    # ══════════════════════════════════════════
    #  ACTIONS — Plugins
    # ══════════════════════════════════════════
    # ── Helpers plugins ──────────────────────────────────────────
    def _log_plugin(self, text):
        def _do():
            self._plugin_log.configure(state="normal")
            self._plugin_log.insert("end", text + "\n")
            self._plugin_log.see("end")
            self._plugin_log.configure(state="disabled")
        self.after(0, _do)

    def _get_plugins_dir(self) -> str | None:
        """Retourne le chemin vers carbon/plugins, ou None si introuvable."""
        # 1. Override manuel
        srv = self.cfg.get("server_dir_override", "").strip()
        if not srv:
            install_path = self.cfg.get("install_path", "")
            srv = ServerProcess.find_rust_exe(install_path) or ""
        if not srv:
            return None
        d = os.path.join(srv, "carbon", "plugins")
        return d if os.path.exists(d) else None

    def _install_plugin(self, slug: str, display_name: str | None = None, status_lbl=None):
        """Télécharge un plugin depuis uMod et l'installe dans carbon/plugins."""
        if not slug:
            self._log_plugin("⚠️  Entrez un nom de plugin (slug).")
            return

        plugins_dir = self._get_plugins_dir()
        if not plugins_dir:
            self._log_plugin("❌  Dossier carbon/plugins introuvable.")
            self._log_plugin("    → Installez Carbon d'abord, ou définissez le dossier serveur.")
            messagebox.showwarning("Plugins",
                "Dossier carbon/plugins introuvable.\nInstallez Carbon ou définissez le dossier serveur dans l'onglet Installation.")
            return

        label = display_name or slug
        self._log_plugin(f"🔍  Recherche de '{label}' sur uMod…")
        if status_lbl:
            self.after(0, lambda: status_lbl.configure(text="⏳", text_color=ORANGE))

        def _do():
            try:
                # 1. Récupérer les infos du plugin via l'API uMod
                api_url = f"https://umod.org/plugins/{slug}.json"
                req = urllib.request.Request(api_url, headers={"User-Agent": "RustServerManager/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())

                download_url = data.get("download_url") or data.get("url")
                plugin_name  = data.get("name", label)
                version      = data.get("version", "?")

                if not download_url:
                    self._log_plugin(f"❌  URL de téléchargement introuvable pour '{slug}'.")
                    if status_lbl:
                        self.after(0, lambda: status_lbl.configure(text="✗", text_color=RED))
                    return

                self._log_plugin(f"📥  Téléchargement : {plugin_name} v{version}…")

                # 2. Télécharger le fichier .cs
                req2 = urllib.request.Request(download_url, headers={"User-Agent": "RustServerManager/1.0"})
                with urllib.request.urlopen(req2, timeout=30) as resp2:
                    content = resp2.read()

                # 3. Sauvegarder dans carbon/plugins/
                filename   = f"{plugin_name}.cs"
                dest_path  = os.path.join(plugins_dir, filename)
                with open(dest_path, "wb") as f:
                    f.write(content)

                self._log_plugin(f"✅  {plugin_name} v{version} installé  →  {filename}")
                if status_lbl:
                    self.after(0, lambda: status_lbl.configure(text="⬤", text_color=GREEN))

                # Rafraîchir la liste
                self.after(300, self._refresh_plugins)

            except urllib.error.HTTPError as e:
                self._log_plugin(f"❌  Plugin '{slug}' introuvable sur uMod (HTTP {e.code}).")
                self._log_plugin(f"    Vérifiez le slug sur : https://umod.org/games/rust")
                if status_lbl:
                    self.after(0, lambda: status_lbl.configure(text="✗", text_color=RED))
            except Exception as e:
                self._log_plugin(f"❌  Erreur : {e}")
                if status_lbl:
                    self.after(0, lambda: status_lbl.configure(text="✗", text_color=RED))

        threading.Thread(target=_do, daemon=True).start()

    def _check_installed_status(self):
        """Met à jour les indicateurs ⬤/○ selon les plugins déjà dans carbon/plugins."""
        plugins_dir = self._get_plugins_dir()
        if not plugins_dir or not hasattr(self, "_plugin_btn_refs"):
            return
        try:
            installed_files = {f.lower() for f in os.listdir(plugins_dir)}
        except Exception:
            return
        for slug, (btn, lbl) in self._plugin_btn_refs.items():
            slug_norm = slug.replace("-", "").lower()
            found = any(slug_norm in f.replace("-", "").replace("_", "").lower()
                        for f in installed_files)
            if found:
                lbl.configure(text="⬤", text_color=GREEN)
                btn.configure(text="✅ Installé", fg_color="#1a3a1a", hover_color="#1a3a1a", state="normal")

    def _refresh_plugins(self):
        for w in self._plugin_list.winfo_children():
            w.destroy()

        plugins_dir = self._get_plugins_dir()

        if not plugins_dir:
            ctk.CTkLabel(self._plugin_list,
                         text="Dossier carbon/plugins introuvable. Installez Carbon d'abord.",
                         text_color=GRAY_TXT).pack(pady=8)
            return

        plugins = [f for f in os.listdir(plugins_dir) if f.endswith((".cs", ".dll"))]

        if not plugins:
            ctk.CTkLabel(self._plugin_list,
                         text="Aucun plugin installé. Utilisez les boutons 'Installer' ci-dessous.",
                         text_color=GRAY_TXT).pack(pady=8)
            return

        for p in sorted(plugins):
            row = ctk.CTkFrame(self._plugin_list, fg_color=CARD_BG2, corner_radius=8)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="🧩", font=ctk.CTkFont(size=14)).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(row, text=p, font=ctk.CTkFont(size=12), anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="🗑 Supprimer", width=110, height=26,
                          fg_color="#3a1a1a", hover_color="#5a1a1a",
                          font=ctk.CTkFont(size=11),
                          command=lambda fp=os.path.join(plugins_dir, p): self._delete_plugin(fp)
                          ).pack(side="right", padx=8, pady=6)
            ctk.CTkLabel(row, text="✅ Chargé", text_color=GREEN,
                         font=ctk.CTkFont(size=11)).pack(side="right", padx=4)

    def _delete_plugin(self, filepath: str):
        name = os.path.basename(filepath)
        if messagebox.askyesno("Supprimer", f"Supprimer le plugin :\n{name} ?"):
            try:
                os.remove(filepath)
                self._log_plugin(f"🗑  {name} supprimé.")
                self._refresh_plugins()
                self._check_installed_status()
            except Exception as e:
                self._log_plugin(f"❌  Erreur suppression : {e}")

    # ══════════════════════════════════════════
    #  ACTIONS — Installation
    # ══════════════════════════════════════════
    def _get_install_path(self, require_server=False):
        p = self.cfg.get("install_path", "")
        if not p:
            messagebox.showwarning("Attention", "Définissez d'abord le dossier d'installation\n(onglet Installation → Parcourir).")
            return None
        if require_server and not ServerProcess.find_rust_exe(p):
            messagebox.showwarning("Attention", "Installez d'abord le serveur Rust (étape 2).")
            return None
        return p

    def _install_steamcmd(self):
        install_path = self._get_install_path()
        if not install_path:
            return
        self._show("install")

        def _do():
            try:
                sc_dir = os.path.join(install_path, "steamcmd")
                os.makedirs(sc_dir, exist_ok=True)

                self._log_install("📥  Téléchargement de SteamCMD…")
                self._set_progress(0.1)

                zip_path = os.path.join(sc_dir, "steamcmd.zip")
                urllib.request.urlretrieve(STEAMCMD_URL, zip_path)

                self._log_install("📦  Extraction…")
                self._set_progress(0.6)

                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(sc_dir)
                os.remove(zip_path)

                self._set_progress(1.0)
                self._log_install(f"✅  SteamCMD installé dans : {sc_dir}")
            except Exception as e:
                self._log_install(f"❌  Erreur : {e}")
                self._set_progress(0)

        threading.Thread(target=_do, daemon=True).start()

    def _install_rust(self):
        install_path = self._get_install_path()
        if not install_path:
            return

        sc_exe = os.path.join(install_path, "steamcmd", "steamcmd.exe")
        if not os.path.exists(sc_exe):
            messagebox.showwarning("Attention", "Installez d'abord SteamCMD (étape 1).")
            return

        self._show("install")

        def _do():
            self._log_install("📥  Installation du serveur Rust (~10 Go). Patience…")
            self._log_install("    SteamCMD télécharge le serveur. Cela peut prendre 15-30 min.")
            self._set_progress(0.05)

            # Méthode script-file : évite tout problème de guillemets/espaces dans le chemin
            script_path = os.path.join(install_path, "steamcmd", "install_rust.txt")
            try:
                with open(script_path, "w", encoding="utf-8") as sf:
                    sf.write(f'force_install_dir "{install_path}"\n')
                    sf.write("login anonymous\n")
                    sf.write(f"app_update {RUST_APP_ID} validate\n")
                    sf.write("quit\n")
            except Exception as e:
                self._log_install(f"❌  Impossible d'écrire le script SteamCMD : {e}")
                return

            cmd = f'"{sc_exe}" +runscript "{script_path}"'
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    shell=True,
                )
                for line in proc.stdout:
                    l = line.rstrip()
                    if l:
                        self._log_install(l)
                proc.wait()

                # Auto-détection de l'emplacement réel après installation
                found = ServerProcess.find_rust_exe(install_path)
                if found:
                    self._set_progress(1.0)
                    self._log_install("✅  Serveur Rust installé !")
                    self._log_install(f"   RustDedicated.exe → {found}")
                    if found != install_path:
                        self._log_install(f"ℹ️  Note : le serveur est dans un sous-dossier.")
                        self._log_install(f"   Le logiciel le trouvera automatiquement au démarrage.")
                else:
                    self._log_install("⚠️  Installation terminée mais RustDedicated.exe introuvable.")
                    self._log_install(f"   Vérifiez manuellement dans : {install_path}")
            except Exception as e:
                self._log_install(f"❌  Erreur : {e}")
                self._set_progress(0)

        threading.Thread(target=_do, daemon=True).start()

    def _install_carbon(self):
        install_path = self._get_install_path(require_server=True)
        if not install_path:
            return
        self._show("install")

        def _do():
            try:
                # Trouver le vrai dossier du serveur (gère l'installation dans un sous-dossier)
                server_dir = ServerProcess.find_rust_exe(install_path) or install_path
                self._log_install(f"ℹ️  Dossier serveur cible : {server_dir}")

                self._log_install("🔍  Récupération de la dernière version de Carbon…")
                self._set_progress(0.1)

                req = urllib.request.Request(
                    CARBON_API,
                    headers={"User-Agent": "RustServerManager/1.0"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())

                asset_url = None
                for asset in data.get("assets", []):
                    name = asset["name"].lower()
                    if "windows" in name and name.endswith(".zip"):
                        asset_url = asset["browser_download_url"]
                        asset_name = asset["name"]
                        break

                if not asset_url:
                    self._log_install("❌  Asset Windows introuvable dans la release GitHub.")
                    self._log_install("    Téléchargez manuellement : https://github.com/CarbonCommunity/Carbon/releases")
                    return

                self._log_install(f"📥  Téléchargement : {asset_name}")
                self._set_progress(0.2)

                zip_path = os.path.join(server_dir, "_carbon_tmp.zip")
                urllib.request.urlretrieve(asset_url, zip_path)

                self._log_install("📦  Extraction de Carbon dans le dossier serveur…")
                self._set_progress(0.85)

                with zipfile.ZipFile(zip_path, "r") as z:
                    z.extractall(server_dir)
                os.remove(zip_path)

                plugins_dir = os.path.join(server_dir, "carbon", "plugins")
                os.makedirs(plugins_dir, exist_ok=True)

                self._set_progress(1.0)
                self._log_install("✅  Carbon installé avec succès !")
                self._log_install(f"   Plugins → {plugins_dir}")
                self._log_install("   Placez vos plugins .cs dans ce dossier.")
            except Exception as e:
                self._log_install(f"❌  Erreur : {e}")
                self._set_progress(0)

        threading.Thread(target=_do, daemon=True).start()

    # ══════════════════════════════════════════
    #  TAB: MISES À JOUR
    # ══════════════════════════════════════════
    def _tab_updates(self):
        frame = ctk.CTkScrollableFrame(self._main, fg_color="transparent",
                                       scrollbar_button_color="#1e2035")
        self.tabs["updates"] = frame
        h1(frame, "Mises à jour automatiques")
        ctk.CTkLabel(frame,
                     text="Partagez le logiciel : il se mettra à jour automatiquement depuis votre GitHub",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=30, pady=(0, 20))

        # ── Version courante ──
        ver_card = card(frame)
        ver_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(ver_card, "  ℹ️  VERSION COURANTE")
        ver_row = ctk.CTkFrame(ver_card, fg_color="transparent")
        ver_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(ver_row, text=f"Version installée :", width=180, anchor="w").pack(side="left")
        ctk.CTkLabel(ver_row, text=f"v{APP_VERSION}", text_color=GREEN,
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(ver_row, text="🔍 Vérifier maintenant", height=34, width=180,
                      fg_color="transparent", border_width=1, border_color=ACCENT,
                      command=self._manual_check_update).pack(side="right")

        self._update_status_lbl = ctk.CTkLabel(ver_card, text="",
                                                text_color=GRAY_TXT, font=ctk.CTkFont(size=12))
        self._update_status_lbl.pack(anchor="w", padx=16, pady=(0, 10))

        # ── Configuration GitHub ──
        gh_card = card(frame)
        gh_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(gh_card, "  🐙  CONFIGURATION GITHUB")

        ctk.CTkLabel(gh_card,
                     text="Entrez votre dépôt GitHub (format :  username/nom-du-repo)",
                     text_color=GRAY_TXT, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16)

        repo_row = ctk.CTkFrame(gh_card, fg_color="transparent")
        repo_row.pack(fill="x", padx=16, pady=(6, 14))
        self._repo_var = tk.StringVar(value=self.cfg.get("github_repo", GITHUB_REPO))
        ctk.CTkEntry(repo_row, textvariable=self._repo_var, height=38,
                     placeholder_text="Ex:  dylan47/rust-server-manager",
                     font=ctk.CTkFont(size=12)).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(repo_row, text="💾 Sauver", width=100, height=38,
                      command=self._save_github_repo).pack(side="left")

        # ── Guide de mise en place ──
        guide_card = card(frame)
        guide_card.pack(fill="x", padx=30, pady=(0, 12))
        section_label(guide_card, "  📖  COMMENT METTRE EN PLACE LE SYSTÈME (5 min)")

        steps = [
            ("1", "Créer un compte GitHub", "Gratuit sur github.com — si vous n'en avez pas déjà un"),
            ("2", "Créer un dépôt public", "Sur github.com → New repository → nommez-le 'rust-server-manager'"),
            ("3", "Uploader le logiciel", "Glissez RustServerManager.py dans votre dépôt GitHub"),
            ("4", "Créer une Release", "Dépôt → Releases → Create a new release → Tag: v1.1.0"),
            ("5", "Joindre le fichier .py", "Dans la release, uploadez le fichier RustServerManager.py mis à jour"),
            ("6", "Configurer ici", "Collez votre dépôt (username/nom-repo) dans le champ ci-dessus"),
            ("7", "Distribuer", "Partagez RustServerManager.py + Lancer_RustManager.bat — les mises à jour sont automatiques !"),
        ]

        for num, title, desc in steps:
            row = ctk.CTkFrame(guide_card, fg_color=CARD_BG2, corner_radius=8)
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=num, width=28, height=28, fg_color=ACCENT2,
                         corner_radius=14, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(10, 10), pady=8)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, pady=8)
            ctk.CTkLabel(info, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                         anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=desc, text_color=GRAY_TXT,
                         font=ctk.CTkFont(size=11), anchor="w").pack(anchor="w")

        ctk.CTkFrame(guide_card, height=8, fg_color="transparent").pack()

        # ── Liens ──
        links = ctk.CTkFrame(frame, fg_color="transparent")
        links.pack(fill="x", padx=30, pady=(0, 24))
        ctk.CTkButton(links, text="🐙  Ouvrir GitHub", height=38, width=160,
                      command=lambda: webbrowser.open("https://github.com")).pack(side="left", padx=(0, 10))
        ctk.CTkButton(links, text="📘  Aide GitHub Releases", height=38, width=200,
                      fg_color="transparent", border_width=1, border_color="#2a2d4a",
                      command=lambda: webbrowser.open(
                          "https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository"
                      )).pack(side="left")

    def _save_github_repo(self):
        repo = self._repo_var.get().strip()
        self.cfg.set("github_repo", repo)
        self.cfg.save()
        messagebox.showinfo("Sauvegardé",
            f"Dépôt GitHub configuré :\n{repo}\n\n"
            "Le logiciel vérifiera les mises à jour au prochain démarrage.")

    def _manual_check_update(self):
        # Utiliser le repo sauvegardé ou la constante
        import importlib, types
        repo = self.cfg.get("github_repo", GITHUB_REPO)
        if not repo:
            messagebox.showwarning("Pas configuré",
                "Configurez d'abord votre dépôt GitHub dans le champ ci-dessous.")
            return
        self._update_status_lbl.configure(text="🔍  Vérification en cours…", text_color=GRAY_TXT)

        def _cb(version, url):
            if version:
                self.after(0, lambda: self._update_status_lbl.configure(
                    text=f"🆕  Nouvelle version disponible : v{version}",
                    text_color=GREEN))
                self.after(0, lambda: self._show_update_banner(version, url))
            else:
                self.after(0, lambda: self._update_status_lbl.configure(
                    text=f"✅  Vous avez la dernière version (v{APP_VERSION})",
                    text_color=GREEN))

        # Patcher temporairement GITHUB_REPO pour utiliser le repo sauvegardé
        original = globals().get("GITHUB_REPO", "")
        import builtins
        # On passe directement l'URL à Updater
        def _check_with_repo(cb):
            if not repo:
                cb(None, None)
                return
            def _do():
                try:
                    url = f"https://api.github.com/repos/{repo}/releases/latest"
                    req = urllib.request.Request(url, headers={"User-Agent": "RustServerManager"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode())
                    latest_tag = data.get("tag_name", "0.0.0")
                    latest_ver = Updater._parse_version(latest_tag)
                    current_ver = Updater._parse_version(APP_VERSION)
                    if latest_ver > current_ver:
                        dl_url = ""
                        for asset in data.get("assets", []):
                            if asset["name"].endswith(".py"):
                                dl_url = asset["browser_download_url"]
                                break
                        if not dl_url:
                            dl_url = data.get("zipball_url", "")
                        cb(latest_tag, dl_url)
                    else:
                        cb(None, None)
                except Exception as e:
                    self.after(0, lambda: self._update_status_lbl.configure(
                        text=f"❌  Erreur : {e}", text_color=RED))
                    cb(None, None)
            threading.Thread(target=_do, daemon=True).start()

        _check_with_repo(_cb)


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
