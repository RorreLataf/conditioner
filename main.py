#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI кондиционера (Tkinter + CAN)
— Вкладки состояния: «Cостояние кондиционера» и «Cостояние инвертора».
— Вкладки параметров: «Скорости вентиляторов» и «Пороги температуры».
— Лог (GUI+консоль), автодетект COM для slcan.
— Телеметрия контроллера (0x5E0100) и инвертора (0x5E0200).
— Расшифровка состояния (Main/Sub) и скоростей вентиляторов (нибблы).
— Диаграммы скоростей: проценты меняются только после «Отправить скорости».
— Таймаут телеметрии: 10 c — сброс на «--/—».
— START/STOP: в последнем байте уставка из блока «Состояние кондиционера».
— SET: в байте2 0x00 при Main=ожидание, иначе 0x20; последний байт — уставка из блока «Команды».
— Инвертор: «Main» из байта 7, «Sub» из байта 6; ошибки — биты байта 5.
"""
from __future__ import annotations
import threading, queue, time
from dataclasses import dataclass
from typing import Optional, Dict, List, Any
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import can
except Exception:
    can = None
try:
    import yaml
except Exception:
    yaml = None


# ======================= Конфигурация CAN =======================
@dataclass
class CANConfig:
    iface: str = "slcan"
    channel: str = ""             # автодетект COM если пусто
    bitrate: int = 250000
    messages: Dict[str, Any] = None
    telemetry_id: int = 0x5E0100
    telemetry_ext: bool = True
    inverter_id: int = 0x5E0200
    inverter_ext: bool = True

    @staticmethod
    def load_from_file(path: str) -> "CANConfig":
        if yaml is None:
            raise RuntimeError("pyyaml не установлен: pip install pyyaml")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cfg = CANConfig()
        bus = data.get("bus", {}) or {}
        cfg.iface = bus.get("interface", cfg.iface)
        cfg.channel = bus.get("channel", cfg.channel)
        cfg.bitrate = int(bus.get("bitrate", cfg.bitrate))
        cfg.messages = data.get("messages", {}) or {}

        telem = cfg.messages.get("TELEMETRY", {}) if cfg.messages else {}
        try:
            tid = telem.get("id", cfg.telemetry_id)
            cfg.telemetry_id = int(tid, 0) if isinstance(tid, str) else int(tid)
        except Exception:
            cfg.telemetry_id = 0x5E0100
        cfg.telemetry_ext = bool(telem.get("extended", True))

        inv = cfg.messages.get("INVERTER_TELEMETRY", {}) if cfg.messages else {}
        try:
            iid = inv.get("id", cfg.inverter_id)
            cfg.inverter_id = int(iid, 0) if isinstance(iid, str) else int(iid)
        except Exception:
            cfg.inverter_id = 0x5E0200
        cfg.inverter_ext = bool(inv.get("extended", True))
        return cfg


# ======================== Клиент CAN ============================
class CANClient:
    def __init__(self, cfg: CANConfig, rx_queue: queue.Queue):
        self.cfg = cfg
        self.rx_queue = rx_queue
        self.bus: Optional[can.BusABC] = None
        self._stop_evt = threading.Event()
        self._reader: Optional[threading.Thread] = None

    def open(self):
        if can is None:
            raise RuntimeError("python-can не установлен: pip install python-can")

        channel = self.cfg.channel
        if self.cfg.iface.lower() == "slcan" and (not channel or channel.strip() == ""):
            try:
                from serial.tools import list_ports  # type: ignore
                ports = list(list_ports.comports())
                preferred = [p.device for p in ports
                             if ("canable" in (p.description or "").lower()
                                 or "lawicel" in (p.description or "").lower())]
                channel = preferred[0] if preferred else (ports[0].device if ports else "")
            except Exception:
                channel = ""
            self.cfg.channel = channel or ""

        self.bus = can.Bus(interface=self.cfg.iface,
                           channel=self.cfg.channel,
                           bitrate=self.cfg.bitrate)
        self._stop_evt.clear()
        self._reader = threading.Thread(target=self._rx_loop, daemon=True)
        self._reader.start()

        self._dbg(f"expecting TELEMETRY id=0x{self.cfg.telemetry_id:X} ext={self.cfg.telemetry_ext} len>=8; "
                  f"INVERTER id=0x{self.cfg.inverter_id:X} ext={self.cfg.inverter_ext} len>=3/8; "
                  f"iface={self.cfg.iface} channel={self.cfg.channel or '(auto)'} bitrate={self.cfg.bitrate}")
        self.rx_queue.put("DBG: GUI queue test — if you see this, queue->poll works")

    def close(self):
        self._stop_evt.set()
        try:
            if self.bus:
                self.bus.shutdown()
        except Exception:
            pass
        self.bus = None

    def send_from_key(self, key: str, context: Dict[str, Any] | None = None):
        if not self.bus:
            raise RuntimeError("CAN не открыт")
        msg_def = (self.cfg.messages or {}).get(key)
        if not msg_def:
            raise RuntimeError(f"Нет секции messages.{key}")
        arb_id = int(msg_def.get("id"))
        is_ext = bool(msg_def.get("extended", False))
        data = self._build_data(msg_def, context or {})
        msg = can.Message(arbitration_id=arb_id, is_extended_id=is_ext, data=bytes(data))
        self.bus.send(msg)
        self.rx_queue.put({'type': 'tx', 'id': arb_id, 'ext': is_ext, 'data': list(bytes(data))})

    def _build_data(self, msg_def: Dict[str, Any], ctx: Dict[str, Any]) -> List[int]:
        if "data" in msg_def and msg_def["data"] is not None:
            data = [int(x) & 0xFF for x in msg_def["data"]][:8]
        else:
            tpl = msg_def.get("data_template", [])
            out: List[int] = []
            for item in tpl:
                if isinstance(item, int):
                    out.append(item & 0xFF); continue
                field = item.get("field")
                if field is None:
                    out.append(int(item.get("value", 0)) & 0xFF); continue
                scale = float(item.get("scale", 1.0))
                width = int(item.get("bytes", 1))
                endian = str(item.get("endian", "le")).lower()
                val = ctx.get(field, 0)
                try: num = int(round(float(val) * scale))
                except Exception: num = 0
                if width == 1:
                    out.append(num & 0xFF)
                elif width == 2:
                    b0, b1 = (num & 0xFF), ((num >> 8) & 0xFF)
                    out.extend([b0, b1] if endian == 'le' else [b1, b0])
                elif width == 4:
                    bs = [(num >> (8*i)) & 0xFF for i in range(4)]
                    if endian == 'be': bs.reverse()
                    out.extend(bs)
                else:
                    out.append(num & 0xFF)
                if len(out) >= 8: break
            data = out[:8]
        while len(data) < 8:
            data.append(0)
        return data[:8]

    def _rx_loop(self):
        tid = self.cfg.telemetry_id
        text = self.cfg.telemetry_ext
        iid = self.cfg.inverter_id
        iext = self.cfg.inverter_ext
        while not self._stop_evt.is_set():
            try:
                msg = self.bus.recv(timeout=0.25)
                if msg is None:
                    continue
                got_id = msg.arbitration_id
                got_ext = msg.is_extended_id
                got_len = len(msg.data)
                self._dbg(f"RX id=0x{got_id:X} ext={got_ext} len={got_len}")

                # --- Контроллер кондиционера ---
                if (got_id == tid) and (got_ext == text) and (got_len >= 8):
                    d = bytes(msg.data)
                    self.rx_queue.put({
                        'type': 'telemetry',
                        'err': d[0],
                        'set': d[1],
                        'temp': d[2],
                        'cond': d[3],
                        'fan_raw': d[6],
                        'state_raw': d[7],
                        'raw': list(d)
                    })
                    self.rx_queue.put(
                        f"TELEM set={d[1]} temp={d[2]} cond={d[3]} fan_byte=0x{d[6]:02X} state_byte=0x{d[7]:02X} err={d[0]}"
                    )
                    continue

                # --- Инвертор ---
                if (got_id == iid) and (got_ext == iext) and (got_len >= 3):
                    d = bytes(msg.data)
                    payload = {
                        'type': 'inv',
                        'cur': d[0], 'volt': d[1], 'temp': d[2],
                        'raw': list(d[:max(3, got_len)])
                    }
                    if got_len >= 6:
                        payload['err5'] = d[5]
                    if got_len >= 7:
                        payload['state6'] = d[6]
                    if got_len >= 8:
                        payload['state7'] = d[7]
                    self.rx_queue.put(payload)
                    self.rx_queue.put("INV cur=%d volt=%d temp=%d%s%s%s" % (
                        d[0], d[1], d[2],
                        (f" err5=0x{d[5]:02X}" if got_len >= 6 else ""),
                        (f" st6={d[6]}" if got_len >= 7 else ""),
                        (f" st7={d[7]}" if got_len >= 8 else ""),
                    ))
                    continue

                # Прочее — лог
                self.rx_queue.put(
                    "DBG: not matched → "
                    f"id=0x{got_id:X} ext={got_ext} len={got_len} | "
                    f"telemetry exp: id=0x{tid:X} ext={text} len>=8 ; "
                    f"inverter exp: id=0x{iid:X} ext={iext} len>=3"
                )
                self.rx_queue.put("CAN RX id=0x%X data=%s" % (
                    got_id, ' '.join(f"{b:02X}" for b in msg.data)))

            except Exception as e:
                self.rx_queue.put(f"CANRXERR={e}")
                time.sleep(0.2)

    def _dbg(self, text: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] DBG: {text}"
        print(line, flush=True)
        try:
            self.rx_queue.put(line)
        except Exception:
            pass


# =========================== GUI ==========================================
class ACControllerApp(ttk.Frame):
    MAIN_STATE = {
        0: "выключено",
        1: "тестирование",
        2: "ожидание",
        3: "работа",
        4: "ошибка",
        5: "продувка",
    }
    SUB_STATE = {
        0: "перед выключением",
        1: "выключено",
        2: "работа",
        3: "перед ожиданием",
        4: "ожидание",
    }

    # Инвертор: расшифровки для «Main» (байт 7) и «Sub» (байт 6)
    INV_MAIN = {
        0: "выключено",
        1: "пауза",
        2: "плавное выключение",
        3: "включено",
        4: "перед отключением",
    }
    INV_SUB = {
        0: "выключено",
        1: "включено",
        2: "пауза",
        3: "плавное выключение",
    }

    TIMEOUT_S = 10.0  # таймаут отсутствия телеметрии, сек

    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=10)
        self.master = master
        self.master.title("Кондиционер (CAN)")
        self.grid(sticky="nsew")
        self.master.rowconfigure(0, weight=1)
        self.master.columnconfigure(0, weight=1)

        self._rx_q: queue.Queue = queue.Queue()
        self._client: Optional[CANClient] = None
        self._cfg: Optional[CANConfig] = None

        # Значения по умолчанию
        self.var_cfg_path = tk.StringVar(value="can_messages.yaml")
        self.var_iface = tk.StringVar(value="slcan")
        self.var_channel = tk.StringVar(value="")
        self.var_bitrate = tk.IntVar(value=250000)

        # Телеметрия кондиционера
        self.var_temp = tk.StringVar(value="--")
        self.var_cond = tk.StringVar(value="--")
        self.var_set = tk.StringVar(value="--")
        self.var_state_main = tk.StringVar(value="—")
        self.var_state_sub = tk.StringVar(value="—")
        self.var_err = tk.StringVar(value="нет")
        self._last_main_state: Optional[int] = None  # для логики SET

        # Уставка (для кнопки «Установить»)
        self.var_set_input = tk.IntVar(value=25)

        # Скорости (дефолт 30/60/90)
        self.var_c1 = tk.IntVar(value=30)
        self.var_c2 = tk.IntVar(value=60)
        self.var_c3 = tk.IntVar(value=90)
        self.var_e1 = tk.IntVar(value=30)
        self.var_e2 = tk.IntVar(value=60)
        self.var_e3 = tk.IntVar(value=90)
        self._speed_conf = {
            'c1': self.var_c1.get(), 'c2': self.var_c2.get(), 'c3': self.var_c3.get(),
            'e1': self.var_e1.get(), 'e2': self.var_e2.get(), 'e3': self.var_e3.get(),
        }

        # Пороги температур
        self.var_t1 = tk.IntVar(value=36)
        self.var_t2 = tk.IntVar(value=38)
        self.var_t3 = tk.IntVar(value=2)
        self.var_t4 = tk.IntVar(value=3)

        # Инвертор
        self.var_inv_cur = tk.StringVar(value="--")
        self.var_inv_volt = tk.StringVar(value="--")
        self.var_inv_temp = tk.StringVar(value="--")
        self.var_inv_main = tk.StringVar(value="—")  # Main: байт 7
        self.var_inv_sub  = tk.StringVar(value="—")  # Sub:  байт 6
        self.var_inv_errs = tk.StringVar(value="—")  # Ошибки (битовая маска из байта 5)

        # Скорости из байта 6 кондиционера
        self.var_fan_level_c = tk.IntVar(value=0)   # 0..3
        self.var_fan_level_e = tk.IntVar(value=0)   # 0..3
        self.var_fan_pct_c = tk.IntVar(value=0)     # %
        self.var_fan_pct_e = tk.IntVar(value=0)     # %

        # Таймауты телеметрии
        self._last_ctrl_rx: float = 0.0
        self._last_inv_rx: float = 0.0
        self._ctrl_valid = False
        self._inv_valid = False

        self.var_status = tk.StringVar(value="Отключено")

        self._build_ui()
        self.after(120, self._poll)

    # ---------- UI ----------
    def _build_ui(self):
        # Верх: подключение
        conn = ttk.LabelFrame(self, text="CAN подключение")
        conn.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        conn.columnconfigure(8, weight=1)
        ttk.Label(conn, text="Файл конф.:").grid(row=0, column=0, sticky="e")
        ttk.Entry(conn, textvariable=self.var_cfg_path, width=30).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(conn, text="…", width=3, command=self._browse_cfg).grid(row=0, column=2)
        ttk.Label(conn, text="iface:").grid(row=0, column=3, sticky="e")
        ttk.Combobox(conn, values=["slcan", "socketcan", "gs_usb", "pcan", "kvaser", "nican", "virtual"],
                     textvariable=self.var_iface, width=12).grid(row=0, column=4, padx=4)
        ttk.Label(conn, text="channel:").grid(row=0, column=5, sticky="e")
        ttk.Entry(conn, textvariable=self.var_channel, width=12).grid(row=0, column=6)
        ttk.Label(conn, text="bitrate:").grid(row=0, column=7, sticky="e")
        ttk.Entry(conn, textvariable=self.var_bitrate, width=9).grid(row=0, column=8, sticky="w")
        ttk.Button(conn, text="Подключиться", command=self.on_connect).grid(row=0, column=9, padx=6)
        ttk.Button(conn, text="Отключиться", command=self.on_disconnect).grid(row=0, column=10)

        # ВКЛАДКИ СОСТОЯНИЙ
        nb_state = ttk.Notebook(self)
        nb_state.grid(row=1, column=0, sticky="ew", padx=4, pady=4)

        tab_ac = ttk.Frame(nb_state)
        nb_state.add(tab_ac, text="Cостояние кондиционера")
        self._build_tab_ac_state(tab_ac)

        tab_inv = ttk.Frame(nb_state)
        nb_state.add(tab_inv, text="Cостояние инвертора")
        self._build_tab_inverter_state(tab_inv)

        # Команды
        ctrl = ttk.LabelFrame(self, text="Команды")
        ctrl.grid(row=2, column=0, sticky="ew", padx=4, pady=4)
        ttk.Button(ctrl, text="Запустить", command=self.on_start, width=14).grid(row=0, column=0, padx=4, pady=2)
        ttk.Button(ctrl, text="Остановить", command=self.on_stop, width=14).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(ctrl, text="Уставка, °C:").grid(row=0, column=2, sticky="e")
        ttk.Spinbox(ctrl, from_=16, to=32, increment=1,
                    textvariable=self.var_set_input, width=6).grid(row=0, column=3, padx=4)
        ttk.Button(ctrl, text="Установить", command=self.on_set, width=12).grid(row=0, column=4, padx=4)

        # ВКЛАДКИ ПАРАМЕТРОВ
        nb = ttk.Notebook(self)
        nb.grid(row=3, column=0, sticky="nsew", padx=4, pady=4)
        self.rowconfigure(3, weight=1)

        tab_speed = ttk.Frame(nb)
        nb.add(tab_speed, text="Скорости вентиляторов")
        self._build_tab_speed(tab_speed)

        tab_temp = ttk.Frame(nb)
        nb.add(tab_temp, text="Пороги температуры")
        self._build_tab_temp(tab_temp)

        # Журнал
        logf = ttk.LabelFrame(self, text="Журнал")
        logf.grid(row=4, column=0, sticky="nsew", padx=4, pady=4)
        self.rowconfigure(4, weight=1)
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.txt_log = tk.Text(logf, height=9)
        self.txt_log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logf, command=self.txt_log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.txt_log['yscrollcommand'] = sb.set

        status = ttk.Label(self, textvariable=self.var_status, relief=tk.SUNKEN, anchor="w")
        status.grid(row=5, column=0, sticky="ew", padx=2, pady=(0,2))

    def _build_tab_ac_state(self, parent: ttk.Frame):
        grid = ttk.Frame(parent); grid.pack(fill="x", padx=6, pady=6)
        for c in range(7): grid.columnconfigure(c, weight=1)

        self._stat_cell(grid, 0, "Текущая температура", self.var_temp, "°C")
        self._stat_cell(grid, 1, "T конденсатора", self.var_cond, "°C")
        self._stat_cell(grid, 2, "Уставка", self.var_set, "°C")

        # Состояние кондиционера: две строки
        frm_state = ttk.Frame(grid, padding=6)
        frm_state.grid(row=0, column=3, sticky="nsew")
        ttk.Label(frm_state, text="Состояние").grid(row=0, column=0, sticky="w")
        ttk.Label(frm_state, textvariable=self.var_state_main, font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w")
        ttk.Label(frm_state, textvariable=self.var_state_sub,  font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w")

        self._stat_cell(grid, 4, "Ошибка", self.var_err, "")

        # Компактные диаграммы
        self._fan_gauge_compact(grid, col=5, title="Конденсатор",
                                lvl_var=self.var_fan_level_c, pct_var=self.var_fan_pct_c, canvas_attr="cnv_fan_c")
        self._fan_gauge_compact(grid, col=6, title="Испаритель",
                                lvl_var=self.var_fan_level_e, pct_var=self.var_fan_pct_e, canvas_attr="cnv_fan_e")

    def _build_tab_inverter_state(self, parent: ttk.Frame):
        grid = ttk.Frame(parent); grid.pack(fill="x", padx=6, pady=6)
        for c in range(6): grid.columnconfigure(c, weight=1)
        self._stat_cell(grid, 0, "Ток", self.var_inv_cur, "A")
        self._stat_cell(grid, 1, "Напряжение", self.var_inv_volt, "V")
        self._stat_cell(grid, 2, "Температура", self.var_inv_temp, "°C")

        # Состояние инвертора: «Main/Sub»
        frm_state = ttk.Frame(grid, padding=6)
        frm_state.grid(row=0, column=3, sticky="nsew")
        ttk.Label(frm_state, text="Состояние инвертора").grid(row=0, column=0, sticky="w")
        ttk.Label(frm_state, textvariable=self.var_inv_main, font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w")
        ttk.Label(frm_state, textvariable=self.var_inv_sub,  font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w")

        # Ошибки инвертора (битовая маска из байта 5)
        frm_err = ttk.Frame(grid, padding=6)
        frm_err.grid(row=0, column=4, sticky="nsew")
        ttk.Label(frm_err, text="Ошибки").grid(row=0, column=0, sticky="w")
        ttk.Label(frm_err, textvariable=self.var_inv_errs, wraplength=260, justify="left")\
            .grid(row=1, column=0, sticky="w")

    def _fan_gauge_compact(self, parent: ttk.Frame, col: int, title: str,
                            lvl_var: tk.IntVar, pct_var: tk.IntVar, canvas_attr: str):
        box = ttk.Frame(parent, padding=(4,2))
        box.grid(row=0, column=col, sticky="nsew")
        ttk.Label(box, text=title).grid(row=0, column=0, columnspan=2, sticky="w")
        cnv = tk.Canvas(box, width=60, height=60, highlightthickness=0)
        cnv.grid(row=1, column=0, rowspan=2, padx=(0,6))
        setattr(self, canvas_attr, cnv)
        self._draw_gauge(cnv, pct_var.get())
        ttk.Label(box, textvariable=lvl_var, font=("Segoe UI", 16, "bold")).grid(row=1, column=1, rowspan=2, sticky="e")

    def _draw_gauge(self, canvas: tk.Canvas, percent: int):
        canvas.delete("all")
        p = max(0, min(100, int(percent)))
        canvas.create_oval(6, 6, 54, 54, outline="#ddd", width=8)
        if p >= 100:
            canvas.create_oval(6, 6, 54, 54, outline="green", width=8)
        elif p > 0:
            extent = p * 3.6
            canvas.create_arc(6, 6, 54, 54, start=90, extent=-extent, style="arc", width=8, outline="green")
        canvas.create_text(30, 30, text=f"{p}%", font=("Segoe UI", 9, "bold"))

    def _stat_cell(self, parent, col, title, var, suffix):
        frm = ttk.Frame(parent, padding=6)
        frm.grid(row=0, column=col, sticky="nsew")
        ttk.Label(frm, text=title).grid(row=0, column=0, sticky="w")
        ttk.Label(frm, textvariable=var, font=("Segoe UI", 16, "bold")).grid(row=1, column=0, sticky="w")
        if suffix:
            ttk.Label(frm, text=suffix).grid(row=1, column=1, sticky="w")

    def _build_tab_speed(self, parent: ttk.Frame):
        grids = ttk.Frame(parent); grids.pack(fill="both", expand=True, padx=6, pady=6)
        grids.columnconfigure(0, weight=1); grids.columnconfigure(1, weight=1)

        self._fan_section(grids, "Вентилятор конденсатора",
                          [("Скорость 1", self.var_c1),
                           ("Скорость 2", self.var_c2),
                           ("Скорость 3", self.var_c3)], col=0)
        self._fan_section(grids, "Вентилятор испарителя",
                          [("Скорость 1", self.var_e1),
                           ("Скорость 2", self.var_e2),
                           ("Скорость 3", self.var_e3)], col=1)

        ttk.Button(parent, text="Отправить скорости", command=self.on_send_speeds)\
            .pack(side="bottom", pady=(6,2))

    def _build_tab_temp(self, parent: ttk.Frame):
        grid = ttk.Frame(parent); grid.pack(fill="x", padx=6, pady=6)
        for i in range(4):
            grid.columnconfigure(i*2, weight=0)
            grid.columnconfigure(i*2+1, weight=1)
        self._temp_field(grid, "COND_LEVEL_1", self.var_t1, 0)
        self._temp_field(grid, "COND_LEVEL_2", self.var_t2, 1)
        self._temp_field(grid, "VAPOR_LEVEL_1", self.var_t3, 2)
        self._temp_field(grid, "VAPOR_LEVEL_2", self.var_t4, 3)
        ttk.Button(parent, text="Отправить пороги", command=self.on_send_temps)\
            .pack(side="bottom", pady=(6,2))

    def _browse_cfg(self):
        path = filedialog.askopenfilename(title="Выберите can_messages.yaml",
                                          filetypes=[("YAML", "*.yaml *.yml"), ("Все файлы", "*.*")])
        if path:
            self.var_cfg_path.set(path)

    # ---- UI helpers ----
    def _fan_section(self, parent, title: str, items, col: int):
        box = ttk.LabelFrame(parent, text=title)
        box.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)
        box.columnconfigure(1, weight=1)
        for i, (label, var) in enumerate(items):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="e", padx=(4,6))
            s = ttk.Scale(box, from_=0, to=100, orient="horizontal",
                          command=lambda v, vv=var: vv.set(int(float(v))))
            s.grid(row=i, column=1, sticky="ew", padx=4)
            s.set(var.get())
            e = ttk.Entry(box, textvariable=var, width=5, justify="center")
            e.grid(row=i, column=2, padx=4)
            def on_entry_change(v=var, scale=s):
                try: val = int(v.get())
                except Exception: return
                if val < 0: val = 0
                if val > 100: val = 100
                v.set(val); scale.set(val)
            var.trace_add("write", lambda *a, f=on_entry_change: f())

    def _temp_field(self, parent, title: str, var: tk.IntVar, idx: int):
        ttk.Label(parent, text=title).grid(row=0, column=idx*2, sticky="e", padx=(6,4), pady=2)
        sp = ttk.Spinbox(parent, from_=-127, to=127, increment=1, textvariable=var, width=6)
        sp.grid(row=0, column=idx*2+1, padx=4, pady=2)

    # -------------------- Обработчики --------------------
    def on_connect(self):
        try:
            cfg = CANConfig.load_from_file(self.var_cfg_path.get())
            cfg.iface = self.var_iface.get().strip() or cfg.iface
            cfg.channel = self.var_channel.get().strip() or cfg.channel
            cfg.bitrate = int(self.var_bitrate.get() or cfg.bitrate)
            self._cfg = cfg
            self._client = CANClient(cfg, self._rx_q)
            self._client.open()
            self.var_status.set(f"CAN: {cfg.iface} {cfg.channel or '(auto)'} @ {cfg.bitrate}")
            self._log("CAN подключён")
        except Exception as e:
            messagebox.showerror("Ошибка CAN", str(e))
            self._client = None
            self._cfg = None
            self.var_status.set("Отключено")

    def on_disconnect(self):
        if not self._client:
            return
        try:
            self._client.close()
        finally:
            self._client = None
            self.var_status.set("Отключено")
            self._log("CAN отключён")

    # Получение уставки из блока «Состояние кондиционера»
    def _get_state_setpoint(self) -> Optional[int]:
        s = (self.var_set.get() or "").strip()
        try:
            return int(s)
        except Exception:
            return None

    # Команды
    def on_start(self):
        val = self._get_state_setpoint()
        if val is None:
            messagebox.showwarning("Уставка неизвестна",
                                   "Уставка в блоке «Состояние кондиционера» ещё не получена от контроллера.")
            return
        self._send_can("START", {"value": val})

    def on_stop(self):
        val = self._get_state_setpoint()
        if val is None:
            messagebox.showwarning("Уставка неизвестна",
                                   "Уставка в блоке «Состояние кондиционера» ещё не получена от контроллера.")
            return
        self._send_can("STOP", {"value": val})

    def on_set(self):
        # «Установить» использует уставку из спинбокса (блок «Команды»)
        val = int(self.var_set_input.get())
        main = self._last_main_state
        mode = 0x00 if (main == 2) else 0x20  # 0x00 при Main=ожидание, иначе 0x20
        self._send_can("SET", {"value": val, "mode": mode})

    # Параметры
    def on_send_speeds(self):
        ctx = {
            "c1": int(self.var_c1.get()), "c2": int(self.var_c2.get()), "c3": int(self.var_c3.get()),
            "e1": int(self.var_e1.get()), "e2": int(self.var_e2.get()), "e3": int(self.var_e3.get()),
        }
        self._send_can("PARAMS_SPEED", ctx)
        self._speed_conf.update(ctx)
        self._update_gauges_with_current_levels()

    def _update_gauges_with_current_levels(self):
        lvl_c = int(self.var_fan_level_c.get())
        lvl_e = int(self.var_fan_level_e.get())
        pct_map_c = {0: 0, 1: self._speed_conf['c1'], 2: self._speed_conf['c2'], 3: self._speed_conf['c3']}
        pct_map_e = {0: 0, 1: self._speed_conf['e1'], 2: self._speed_conf['e2'], 3: self._speed_conf['e3']}
        pct_c = pct_map_c.get(lvl_c, 0)
        pct_e = pct_map_e.get(lvl_e, 0)
        self.var_fan_pct_c.set(pct_c)
        self.var_fan_pct_e.set(pct_e)
        if hasattr(self, "cnv_fan_c"): self._draw_gauge(self.cnv_fan_c, pct_c)
        if hasattr(self, "cnv_fan_e"): self._draw_gauge(self.cnv_fan_e, pct_e)

    def on_send_temps(self):
        ctx = {"t1": int(self.var_t1.get()), "t2": int(self.var_t2.get()),
               "t3": int(self.var_t3.get()), "t4": int(self.var_t4.get())}
        self._send_can("PARAMS_TEMP", ctx)

    def _send_can(self, key: str, ctx: Dict[str, Any]):
        if not self._client:
            raise RuntimeError("CAN не подключен")
        self._client.send_from_key(key, ctx)

    # Сбросы при таймауте
    def _reset_ctrl_display(self):
        self.var_temp.set("--")
        self.var_cond.set("--")
        self.var_set.set("--")
        self.var_state_main.set("—")
        self.var_state_sub.set("—")
        self.var_err.set("нет")
        self.var_fan_level_c.set(0)
        self.var_fan_level_e.set(0)
        self._update_gauges_with_current_levels()

    def _reset_inv_display(self):
        self.var_inv_cur.set("--")
        self.var_inv_volt.set("--")
        self.var_inv_temp.set("--")
        self.var_inv_main.set("—")
        self.var_inv_sub.set("—")
        self.var_inv_errs.set("—")

    # Форматирование ошибок инвертора из байта 5
    @staticmethod
    def _format_inv_errors(mask: int) -> str:
        items = []
        if mask & 0x01: items.append("Превышение макс. тока")
        if mask & 0x02: items.append("Не норма U1")
        if mask & 0x04: items.append("Не норма U2")
        if mask & 0x08: items.append("Превышение макс. температуры")
        if mask & 0x10: items.append("Флаг 18В")
        return ", ".join(items) if items else "—"

    # Приём/лог + обновление UI + таймауты
    def _poll(self):
        now = time.time()
        try:
            while True:
                item = self._rx_q.get_nowait()
                if isinstance(item, dict):
                    t = item.get("type")
                    if t == "telemetry":
                        self._last_ctrl_rx = now
                        self._ctrl_valid = True
                        self.var_err.set(str(item.get("err", 0)))
                        self.var_set.set(str(item.get("set", "--")))
                        self.var_temp.set(str(item.get("temp", "--")))
                        self.var_cond.set(str(item.get("cond", "--")))

                        fan_byte = int(item.get("fan_raw", 0))
                        lvl_c = max(0, min(3, (fan_byte >> 4) & 0x0F))
                        lvl_e = max(0, min(3, fan_byte & 0x0F))
                        self.var_fan_level_c.set(lvl_c)
                        self.var_fan_level_e.set(lvl_e)

                        # проценты — только из «подтверждённых» значений
                        self._update_gauges_with_current_levels()

                        state_byte = int(item.get("state_raw", 0))
                        main = (state_byte >> 4) & 0x0F
                        sub  = state_byte & 0x0F
                        self._last_main_state = main
                        main_txt = self.MAIN_STATE.get(main, f"неизв({main})")
                        sub_txt  = self.SUB_STATE.get(sub,  f"неизв({sub})")
                        self.var_state_main.set(f"Main: {main_txt}")
                        self.var_state_sub.set(f"Sub:  {sub_txt}")

                        raw = item.get("raw", [])
                        if raw:
                            self._log("RX TELEM: " + " ".join(f"{b:02X}" for b in raw))

                    elif t == "inv":
                        self._last_inv_rx = now
                        self._inv_valid = True
                        self.var_inv_cur.set(str(item.get("cur", "--")))
                        self.var_inv_volt.set(str(item.get("volt", "--")))
                        self.var_inv_temp.set(str(item.get("temp", "--")))
                        if 'state7' in item:
                            s7 = int(item['state7'])
                            self.var_inv_main.set(f"Main: {self.INV_MAIN.get(s7, f'неизв({s7})')}")
                        if 'state6' in item:
                            s6 = int(item['state6'])
                            self.var_inv_sub.set(f"Sub:  {self.INV_SUB.get(s6, f'неизв({s6})')}")
                        if 'err5' in item:
                            self.var_inv_errs.set(self._format_inv_errors(int(item['err5'])))
                        raw = item.get("raw", [])
                        if raw:
                            self._log("RX INV: " + " ".join(f"{b:02X}" for b in raw))

                    elif t == "tx":
                        data_hex = " ".join(f"{b:02X}" for b in item.get("data", []))
                        self._log(f"TX id=0x{item['id']:X} data={data_hex}")
                else:
                    self._log(str(item))
        except queue.Empty:
            pass

        # Таймауты
        if self._ctrl_valid and (now - self._last_ctrl_rx > self.TIMEOUT_S):
            self._ctrl_valid = False
            self._reset_ctrl_display()
            self._log("DBG: timeout controller telemetry → reset display")

        if self._inv_valid and (now - self._last_inv_rx > self.TIMEOUT_S):
            self._inv_valid = False
            self._reset_inv_display()
            self._log("DBG: timeout inverter telemetry → reset display")

        self.after(100, self._poll)

    def _log(self, text: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        print(line, flush=True)
        self.txt_log.insert(tk.END, line + "\n")
        self.txt_log.see(tk.END)


def main():
    root = tk.Tk()
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "light")
    except Exception:
        pass
    app = ACControllerApp(root)
    root.minsize(950, 650)
    root.mainloop()


if __name__ == "__main__":
    main()
