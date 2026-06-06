import tkinter as tk
from tkinter import messagebox, ttk
import threading
import time
import os
import json
import cv2
import numpy as np
import pydirectinput
from PIL import ImageGrab

# ============================================================
# LETTER BOT - TEMPLATE MATCHING V6
# ------------------------------------------------------------
# Changes in V6:
# 1) All interface text is now English.
# 2) Emergency-stop text was removed from the interface.
# 3) Slot logic was removed.
# 4) Monitor-size presets remain.
# 5) Presets are sorted from larger to smaller resolutions.
# 6) Selected region is saved automatically.
#
# Requirements:
# pip install opencv-python pillow numpy pydirectinput
# ============================================================

pydirectinput.PAUSE = 0
pydirectinput.FAILSAFE = True

TARGET_LETTERS = ["E", "R", "T", "F", "G"]

PRESS_THRESHOLD = 0.80
RESET_THRESHOLD = 0.55
PRESS_DELAY = 0.12

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "letter_templates")
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "letter_bot_settings.json")

# Base region originally calibrated on 2560x1440.
BASE_W = 2560
BASE_H = 1440
BASE_REGION = [1230, 870, 1330, 990]

PRESETS = {
    "4K 3840x2160": [
        round(BASE_REGION[0] * 3840 / BASE_W),
        round(BASE_REGION[1] * 2160 / BASE_H),
        round(BASE_REGION[2] * 3840 / BASE_W),
        round(BASE_REGION[3] * 2160 / BASE_H),
    ],
    "QHD / 2K 2560x1440": BASE_REGION,
    "Full HD 1920x1080": [
        round(BASE_REGION[0] * 1920 / BASE_W),
        round(BASE_REGION[1] * 1080 / BASE_H),
        round(BASE_REGION[2] * 1920 / BASE_W),
        round(BASE_REGION[3] * 1080 / BASE_H),
    ],
    "HD 1366x768": [
        round(BASE_REGION[0] * 1366 / BASE_W),
        round(BASE_REGION[1] * 768 / BASE_H),
        round(BASE_REGION[2] * 1366 / BASE_W),
        round(BASE_REGION[3] * 768 / BASE_H),
    ],
}

SCALES = [0.75, 0.85, 0.95, 1.00, 1.05, 1.15, 1.25]


class RoundedFrame(tk.Canvas):
    def __init__(self, parent, bg="#111827", fill="#1f2937", radius=20, **kwargs):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self.fill = fill
        self.radius = radius
        self.inner = tk.Frame(self, bg=fill)
        self.window_id = self.create_window(0, 0, window=self.inner, anchor="nw")
        self.bind("<Configure>", self._draw)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _draw(self, event=None):
        self.delete("bg")
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        self._round_rect(2, 2, w - 2, h - 2, self.radius, fill=self.fill, outline="", tags="bg")
        self.coords(self.window_id, 12, 10)
        self.itemconfig(self.window_id, width=max(1, w - 24), height=max(1, h - 20))
        self.tag_lower("bg")


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent,
        text,
        command=None,
        width=150,
        height=38,
        radius=16,
        bg="#1f2937",
        fill="#34d399",
        hover="#6ee7b7",
        disabled_fill="#475569",
        fg="#052e20",
        font=("Consolas", 10, "bold")
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )
        self.text = text
        self.command = command
        self.width_v = width
        self.height_v = height
        self.radius = radius
        self.fill = fill
        self.hover = hover
        self.disabled_fill = disabled_fill
        self.fg = fg
        self.font = font
        self.enabled = True

        self._draw(fill)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _draw(self, color):
        self.delete("all")
        self._round_rect(2, 2, self.width_v - 2, self.height_v - 2, self.radius, fill=color, outline="")
        self.create_text(
            self.width_v // 2,
            self.height_v // 2,
            text=self.text,
            fill=self.fg,
            font=self.font
        )

    def _click(self, event=None):
        if self.enabled and self.command:
            self.command()

    def _enter(self, event=None):
        if self.enabled:
            self._draw(self.hover)

    def _leave(self, event=None):
        if self.enabled:
            self._draw(self.fill)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            self.configure(cursor="hand2")
            self._draw(self.fill)
        else:
            self.configure(cursor="")
            self._draw(self.disabled_fill)


class LetterBotV6:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Chain QTE")
        self.root.geometry("560x690")
        self.root.resizable(False, False)
        self.root.configure(bg="#111827")

        self.running = False
        self.region = None
        self.bot_thread = None
        self.total_presses = 0
        self.templates = {}

        self.letter_locked = False
        self.locked_letter = None

        self.settings = {
            "region": BASE_REGION,
            "preset": "QHD / 2K 2560x1440",
            "press_threshold": PRESS_THRESHOLD,
            "reset_threshold": RESET_THRESHOLD
        }

        self._style_combobox()
        self._build_ui()
        self._template_folder_ready()
        self._load_templates()
        self._load_settings()

    # --------------------------------------------------------
    # UI STYLE
    # --------------------------------------------------------
    def _style_combobox(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Dark.TCombobox",
            fieldbackground="#0f172a",
            background="#1e293b",
            foreground="#f8fafc",
            arrowcolor="#38bdf8",
            bordercolor="#334155",
            lightcolor="#334155",
            darkcolor="#334155",
            padding=5
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", "#0f172a")],
            foreground=[("readonly", "#f8fafc")]
        )

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------
    def _save_settings_silent(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.status_label.config(text=f"● Settings could not be saved: {e}", fg="#fb7185")

    def _load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict):
                    reg = data.get("region")
                    preset = data.get("preset")

                    if self._valid_region(reg):
                        self.settings["region"] = reg

                    if preset in PRESETS:
                        self.settings["preset"] = preset

            except Exception:
                pass

        self.preset_var.set(self.settings["preset"])
        self.region = tuple(self.settings["region"])
        self._region_label_update()
        self.status_label.config(text="● Settings loaded. Ready.", fg="#34d399")

    def _valid_region(self, reg):
        return (
            isinstance(reg, list)
            and len(reg) == 4
            and all(isinstance(v, int) for v in reg)
            and reg[2] > reg[0]
            and reg[3] > reg[1]
        )

    def _apply_preset(self, event=None):
        name = self.preset_var.get()
        reg = PRESETS.get(name)

        if not self._valid_region(reg):
            return

        self.region = tuple(reg)
        self.settings["region"] = list(reg)
        self.settings["preset"] = name
        self._region_label_update()
        self._save_settings_silent()
        self.status_label.config(text=f"● Preset applied: {name}", fg="#38bdf8")

    # --------------------------------------------------------
    # INTERFACE
    # --------------------------------------------------------
    def _build_ui(self):
        bg = "#111827"
        card = "#1f2937"
        card2 = "#182235"
        green = "#34d399"
        green_hover = "#6ee7b7"
        red = "#fb7185"
        red_hover = "#fda4af"
        blue = "#38bdf8"
        text = "#f8fafc"
        muted = "#94a3b8"

        tk.Label(
            self.root,
            text="Auto Chain QTE",
            font=("Consolas", 22, "bold"),
            bg=bg,
            fg=green
        ).pack(pady=(12, 0))

        tk.Label(
            self.root,
            text="Template Matching • Monitor Presets • Anti-Spam Lock",
            font=("Consolas", 9),
            bg=bg,
            fg=muted
        ).pack(pady=(0, 8))

        top_card = RoundedFrame(self.root, bg=bg, fill=card2, radius=24, height=66)
        top_card.pack(fill="x", padx=18, pady=(0, 6))

        btn_row = tk.Frame(top_card.inner, bg=card2)
        btn_row.pack(fill="x", expand=True)

        self.start_btn = RoundedButton(
            btn_row,
            text="▶ START",
            width=235,
            height=42,
            radius=20,
            bg=card2,
            fill=green,
            hover=green_hover,
            fg="#052e20",
            command=self.start_bot
        )
        self.start_btn.pack(side="left", padx=(0, 10))

        self.stop_btn = RoundedButton(
            btn_row,
            text="⏹ STOP",
            width=235,
            height=42,
            radius=20,
            bg=card2,
            fill=red,
            hover=red_hover,
            fg="#450a0a",
            command=self.stop_bot
        )
        self.stop_btn.pack(side="left", padx=(10, 0))
        self.stop_btn.set_enabled(False)

        main_row = tk.Frame(self.root, bg=bg)
        main_row.pack(fill="x", padx=18, pady=4)

        frame_letter = RoundedFrame(main_row, bg=bg, fill=card, radius=24, width=210, height=150)
        frame_letter.pack(side="left", padx=(0, 8))

        tk.Label(
            frame_letter.inner,
            text="Last key",
            font=("Consolas", 9),
            bg=card,
            fg=muted
        ).pack(pady=(0, 0))

        self.last_letter_label = tk.Label(
            frame_letter.inner,
            text="—",
            font=("Consolas", 54, "bold"),
            bg=card,
            fg=green,
            width=3
        )
        self.last_letter_label.pack(pady=(0, 0))

        self.press_count_label = tk.Label(
            frame_letter.inner,
            text="Total: 0",
            font=("Consolas", 10),
            bg=card,
            fg=text
        )
        self.press_count_label.pack()

        frame_status = RoundedFrame(main_row, bg=bg, fill=card2, radius=24, width=310, height=150)
        frame_status.pack(side="left", padx=(8, 0))

        self.status_label = tk.Label(
            frame_status.inner,
            text="● Waiting",
            font=("Consolas", 9, "bold"),
            bg=card2,
            fg=muted,
            wraplength=270,
            justify="left"
        )
        self.status_label.pack(anchor="w", pady=(4, 4))

        self.score_label = tk.Label(
            frame_status.inner,
            text=f"Press: {PRESS_THRESHOLD:.2f}\nReset: {RESET_THRESHOLD:.2f}",
            font=("Consolas", 9),
            bg=card2,
            fg="#cbd5e1",
            justify="left"
        )
        self.score_label.pack(anchor="w", pady=(2, 0))

        frame_region = RoundedFrame(self.root, bg=bg, fill=card, radius=24, height=130)
        frame_region.pack(fill="x", padx=18, pady=6)

        tk.Label(
            frame_region.inner,
            text="1) Screen region",
            font=("Consolas", 11, "bold"),
            bg=card,
            fg=blue
        ).pack(anchor="w", pady=(0, 5))

        tk.Label(
            frame_region.inner,
            text="Monitor size preset",
            font=("Consolas", 9),
            bg=card,
            fg=muted
        ).pack(anchor="w")

        self.preset_var = tk.StringVar(value="QHD / 2K 2560x1440")
        self.preset_combo = ttk.Combobox(
            frame_region.inner,
            textvariable=self.preset_var,
            values=list(PRESETS.keys()),
            state="readonly",
            style="Dark.TCombobox",
            font=("Consolas", 9),
            width=38
        )
        self.preset_combo.pack(fill="x", pady=(2, 8))
        self.preset_combo.bind("<<ComboboxSelected>>", self._apply_preset)

        self.region_label = tk.Label(
            frame_region.inner,
            text="No region selected",
            font=("Consolas", 9),
            bg=card,
            fg=muted,
            wraplength=490,
            justify="left"
        )
        self.region_label.pack(anchor="w", pady=(0, 8))


        frame_templates = RoundedFrame(self.root, bg=bg, fill=card, radius=24, height=170)
        frame_templates.pack(fill="x", padx=18, pady=6)

        tk.Label(
            frame_templates.inner,
            text="2) Letter templates",
            font=("Consolas", 11, "bold"),
            bg=card,
            fg=green
        ).pack(anchor="w", pady=(0, 4))

        self.template_label = tk.Label(
            frame_templates.inner,
            text="Checking templates...",
            font=("Consolas", 9),
            bg=card,
            fg=muted,
            wraplength=490,
            justify="left"
        )
        self.template_label.pack(anchor="w", pady=(0, 8))

        template_btns = tk.Frame(frame_templates.inner, bg=card)
        template_btns.pack(fill="x", pady=(0, 4))

        RoundedButton(
            template_btns,
            text="Reload Templates",
            width=235,
            height=38,
            radius=18,
            bg=card,
            fill="#22c55e",
            hover="#86efac",
            fg="#052e16",
            command=self._load_templates
        ).pack(side="left", padx=(0, 8))

        RoundedButton(
            template_btns,
            text="Open Folder",
            width=235,
            height=38,
            radius=18,
            bg=card,
            fill="#14b8a6",
            hover="#5eead4",
            fg="#042f2e",
            command=self._open_template_folder
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            frame_templates.inner,
            text="Files: E.png, R.png, T.png, F.png, G.png",
            font=("Consolas", 8),
            bg=card,
            fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            self.root,
            text="If it spams, increase PRESS_THRESHOLD to 0.85–0.90. If it misses, lower it to 0.70–0.75.",
            font=("Consolas", 8),
            bg=bg,
            fg="#64748b"
        ).pack(pady=(4, 0))

    # --------------------------------------------------------
    # TEMPLATES
    # --------------------------------------------------------
    def _template_folder_ready(self):
        os.makedirs(TEMPLATE_DIR, exist_ok=True)

    def _open_template_folder(self):
        try:
            os.startfile(TEMPLATE_DIR)
        except Exception as e:
            messagebox.showerror("Error", f"Folder could not be opened:\n{e}")

    def _load_templates(self):
        self.templates = {}
        missing = []
        loaded = []

        for letter in TARGET_LETTERS:
            file_path = os.path.join(TEMPLATE_DIR, f"{letter}.png")

            if not os.path.exists(file_path):
                missing.append(f"{letter}.png")
                continue

            img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                missing.append(f"{letter}.png")
                continue

            variants = self._create_template_variants(img)
            self.templates[letter] = variants
            loaded.append(f"{letter}.png")

        if missing:
            self.template_label.config(
                text=(
                    f"Loaded: {', '.join(loaded) if loaded else 'none'}\n"
                    f"Missing: {', '.join(missing)}"
                ),
                fg="#fb7185"
            )
        else:
            self.template_label.config(
                text=f"All templates loaded: {', '.join(loaded)}",
                fg="#34d399"
            )

    def _create_template_variants(self, img):
        variants = []
        processed_list = self._preprocess_two_modes(img)

        for processed in processed_list:
            h, w = processed.shape[:2]
            for scale in SCALES:
                nw = max(5, int(w * scale))
                nh = max(5, int(h * scale))
                resized = cv2.resize(processed, (nw, nh), interpolation=cv2.INTER_AREA)
                variants.append(resized)

        return variants

    # --------------------------------------------------------
    # REGION
    # --------------------------------------------------------
    def select_region(self):
        self.status_label.config(text="● Region selection starts in 4 seconds...", fg="#c084fc")
        self.root.after(4000, self._start_region_selection)

    def _start_region_selection(self):
        self.root.withdraw()
        time.sleep(0.3)
        RegionSelector(self.root, self._region_selected)

    def _region_selected(self, region):
        self.root.deiconify()

        if region:
            self.region = region
            self.settings["region"] = list(self.region)
            self.settings["preset"] = self.preset_var.get()
            self._region_label_update()
            self._save_settings_silent()
            self.status_label.config(text="● Region selected and saved automatically.", fg="#38bdf8")
        else:
            self.status_label.config(text="● Region selection cancelled.", fg="#94a3b8")

    def _region_label_update(self):
        if not self.region:
            self.region_label.config(text="No region selected", fg="#94a3b8")
            return

        x1, y1, x2, y2 = self.region
        self.region_label.config(
            text=f"x:{x1} y:{y1} → x:{x2} y:{y2}  ({x2 - x1}×{y2 - y1}px)",
            fg="#f8fafc"
        )

    # --------------------------------------------------------
    # BOT
    # --------------------------------------------------------
    def start_bot(self):
        if not self.region:
            messagebox.showwarning("Warning", "Select a screen region or choose a preset first.")
            return

        if len(self.templates) < len(TARGET_LETTERS):
            messagebox.showwarning(
                "Warning",
                "Prepare these template files first: E.png, R.png, T.png, F.png, G.png."
            )
            return

        self.running = True
        self.total_presses = 0
        self.letter_locked = False
        self.locked_letter = None

        self.last_letter_label.config(text="—", fg="#34d399")
        self.press_count_label.config(text="Total: 0")

        self.start_btn.set_enabled(False)
        self.stop_btn.set_enabled(True)
        self.status_label.config(text="● Bot is running...", fg="#34d399")

        self.bot_thread = threading.Thread(target=self._bot_loop, daemon=True)
        self.bot_thread.start()

    def stop_bot(self):
        self.running = False
        self.start_btn.set_enabled(True)
        self.stop_btn.set_enabled(False)
        self.status_label.config(text="● Stopped", fg="#fb7185")

    def _preprocess_two_modes(self, gray):
        if len(gray.shape) == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_RGB2GRAY)

        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        _, normal = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        _, inverted = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        return [normal, inverted]

    def _find_letter(self, frame_gray):
        screen_variants = self._preprocess_two_modes(frame_gray)

        best_letter = None
        best_score = -1.0

        for screen in screen_variants:
            screen_h, screen_w = screen.shape[:2]

            for letter, template_list in self.templates.items():
                for template in template_list:
                    t_h, t_w = template.shape[:2]

                    if t_h > screen_h or t_w > screen_w:
                        continue

                    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(result)

                    if max_val > best_score:
                        best_score = max_val
                        best_letter = letter

        return best_letter, best_score

    def _bot_loop(self):
        while self.running:
            try:
                img = ImageGrab.grab(bbox=self.region)
                frame = np.array(img)
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

                letter, score = self._find_letter(gray)

                if self.letter_locked:
                    if score < RESET_THRESHOLD:
                        self.letter_locked = False
                        self.locked_letter = None
                        self.root.after(
                            0,
                            lambda s=score: self.status_label.config(
                                text=f"● Reset. Waiting for next letter... score: {s:.2f}",
                                fg="#34d399"
                            )
                        )
                    else:
                        self.root.after(
                            0,
                            lambda l=letter, s=score: self.status_label.config(
                                text=f"● Locked: waiting for the letter to disappear | {l} | score: {s:.2f}",
                                fg="#c084fc"
                            )
                        )

                    time.sleep(0.02)
                    continue

                if letter and score >= PRESS_THRESHOLD:
                    pydirectinput.press(letter.lower())
                    self.total_presses += 1
                    self.letter_locked = True
                    self.locked_letter = letter

                    self.root.after(
                        0,
                        lambda l=letter, s=score: self._update_ui_after_press(l, s)
                    )

                    time.sleep(PRESS_DELAY)

                else:
                    self.root.after(
                        0,
                        lambda l=letter, s=score: self.status_label.config(
                            text=f"● Watching... best: {l} | score: {s:.2f} | threshold: {PRESS_THRESHOLD:.2f}",
                            fg="#38bdf8"
                        )
                    )

                time.sleep(0.02)

            except Exception as e:
                self.root.after(
                    0,
                    lambda err=str(e): self.status_label.config(
                        text=f"● Error: {err}",
                        fg="#fb7185"
                    )
                )
                time.sleep(0.2)

    def _update_ui_after_press(self, letter, score):
        self.last_letter_label.config(text=letter, fg="#f8fafc")
        self.status_label.config(
            text=f"● Pressed '{letter}' once | score: {score:.2f}. Waiting for it to disappear.",
            fg="#34d399"
        )
        self.press_count_label.config(text=f"Total: {self.total_presses}")
        self.root.after(200, lambda: self.last_letter_label.config(fg="#34d399"))


class RegionSelector:
    def __init__(self, master, callback):
        self.callback = callback
        self.start_x = 0
        self.start_y = 0
        self.rect = None

        self.win = tk.Toplevel(master)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.30)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        self.win.overrideredirect(True)

        self.canvas = tk.Canvas(
            self.win,
            cursor="cross",
            bg="black",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Escape>", lambda e: self._close(None))

        self.canvas.create_text(
            self.win.winfo_screenwidth() // 2,
            42,
            text="Drag to select the screen region | ESC = cancel",
            fill="white",
            font=("Consolas", 15, "bold")
        )

    def on_press(self, e):
        self.start_x, self.start_y = e.x, e.y

        if self.rect:
            self.canvas.delete(self.rect)

        self.rect = self.canvas.create_rectangle(
            e.x,
            e.y,
            e.x,
            e.y,
            outline="#38bdf8",
            width=3
        )

    def on_drag(self, e):
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, e.x, e.y)

    def on_release(self, e):
        x1 = min(self.start_x, e.x)
        y1 = min(self.start_y, e.y)
        x2 = max(self.start_x, e.x)
        y2 = max(self.start_y, e.y)

        if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
            self._close(None)
        else:
            self._close((x1, y1, x2, y2))

    def _close(self, region):
        self.win.destroy()
        self.callback(region)


if __name__ == "__main__":
    root = tk.Tk()
    app = LetterBotV6(root)
    root.mainloop()
