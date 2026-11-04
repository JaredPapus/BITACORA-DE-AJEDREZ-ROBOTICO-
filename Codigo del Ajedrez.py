"""Gran Maestro V7: interfaz premium con tablero texturizado y piezas HD; Stockfish como motor.

Requiere: pip install python-chess
Funciona en Windows con Python 3.14 y se puede portar a Raspberry Pi 5.
"""

from __future__ import annotations

import json
from pathlib import Path
import queue
import random
import shutil
import threading
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
from tkinter import filedialog, messagebox, ttk

import chess
import chess.engine

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "configuracion.json"
ASSETS = BASE / "piezas"

def encontrar_stockfish() -> str:
    """Detecta un motor instalado o depositado en la carpeta del proyecto."""
    comando = shutil.which("stockfish")
    if comando:
        return comando
    for carpeta in (BASE, BASE / "motor"):
        if carpeta.is_dir():
            for archivo in carpeta.iterdir():
                if archivo.is_file() and "stockfish" in archivo.name.lower():
                    if archivo.suffix.lower() == ".exe" or (not archivo.suffix and archivo.stat().st_mode & 0o111):
                        return str(archivo)
    return ""


# Paletas inspiradas en tableros de ajedrez reales.
# Puedes elegir otra desde el panel «Apariencia», sin reiniciar la partida.
TEMAS = {
    "Ébano y oro": {
        "fondo": "#101215", "panel": "#1B1D20", "panel_2": "#24262A",
        "blanco": "#F6F1E8", "muted": "#A6A4A0", "acento": "#D5AE71",
        "casilla_clara": "#EDE0C8", "casilla_oscura": "#876749",
        "seleccion": "#F2C974", "ultimo": "#C7A46E", "jaque": "#D95E5B",
        "luz_origen": "#FFD36E", "luz_destino": "#65C8A2",
        "borde": "#37332F", "cabecera": "#151719", "sutil": "#857F78",
        "boton_hover": "#36383C", "principal_hover": "#E8C68C",
        "texto_boton": "#1D1A17", "resalte": "#3C3530",
        "board_outer": "#151414", "board_trim": "#B99760", "board_glow": "#33291E",
    },
    "Verde torneo": {
        "fondo": "#111819", "panel": "#1C2826", "panel_2": "#293B37",
        "blanco": "#F6F4EC", "muted": "#AAC0B6", "acento": "#D7BE81",
        "casilla_clara": "#EFEEDB", "casilla_oscura": "#718875",
        "seleccion": "#EFC966", "ultimo": "#B6C5A0", "jaque": "#DD6961",
        "luz_origen": "#FDD66F", "luz_destino": "#5BD9B1",
        "borde": "#394943", "cabecera": "#14211F", "sutil": "#859B91",
        "boton_hover": "#395049", "principal_hover": "#E8D3A0",
        "texto_boton": "#20221B", "resalte": "#2D4A40",
        "board_outer": "#14251F", "board_trim": "#BDAF81", "board_glow": "#274239",
    },
    "Pizarra moderna": {
        "fondo": "#101419", "panel": "#1B232B", "panel_2": "#293440",
        "blanco": "#F4F6F5", "muted": "#A1ABB4", "acento": "#D6BD91",
        "casilla_clara": "#E9E9E4", "casilla_oscura": "#788594",
        "seleccion": "#EFC979", "ultimo": "#B1C1C7", "jaque": "#DC6565",
        "luz_origen": "#FFDC7B", "luz_destino": "#67D0B0",
        "borde": "#3A4855", "cabecera": "#151D25", "sutil": "#85909C",
        "boton_hover": "#3C4C5B", "principal_hover": "#F0D4A0",
        "texto_boton": "#1F2428", "resalte": "#2F434C",
        "board_outer": "#151B22", "board_trim": "#B8A88F", "board_glow": "#26343D",
    },
}
COLORES = dict(TEMAS["Ébano y oro"])
TAM_CASILLA = 75
TAM_TABLERO = TAM_CASILLA * 8

PIEZAS = {
    chess.WHITE: {
        chess.PAWN: "♙", chess.KNIGHT: "♘", chess.BISHOP: "♗",
        chess.ROOK: "♖", chess.QUEEN: "♕", chess.KING: "♔",
    },
    chess.BLACK: {
        chess.PAWN: "♟", chess.KNIGHT: "♞", chess.BISHOP: "♝",
        chess.ROOK: "♜", chess.QUEEN: "♛", chess.KING: "♚",
    },
}
NOMBRE_PIEZA = {
    chess.PAWN: "peón", chess.KNIGHT: "caballo", chess.BISHOP: "alfil",
    chess.ROOK: "torre", chess.QUEEN: "dama", chess.KING: "rey",
}


def explicar_sugerencia(tablero: chess.Board, jugada: chess.Move) -> str:
    """Ofrece una explicación concreta sin prometer que una jugada sea infalible."""
    if jugada not in tablero.legal_moves:
        return "La sugerencia ya no corresponde a esta posición."
    pieza = tablero.piece_at(jugada.from_square)
    if not pieza:
        return "Selecciona la pieza indicada y muévela a la casilla iluminada."
    copia = tablero.copy(stack=False)
    copia.push(jugada)
    if copia.is_checkmate():
        return "¡Jaque mate! Esta jugada termina la partida."
    if tablero.is_check():
        return "Tu rey está en jaque. Esta jugada permite salir del peligro."
    if tablero.is_castling(jugada):
        return "Enroca para poner a salvo el rey y desarrollar la torre."
    if jugada.promotion:
        return "Tu peón llega a la última fila y puede convertirse en una pieza más fuerte."
    if tablero.is_capture(jugada):
        victima = tablero.piece_at(jugada.to_square)
        nombre = NOMBRE_PIEZA[victima.piece_type] if victima else "peón"
        return f"Puedes capturar un {nombre} rival. Observa qué piezas protegen esa casilla."
    if copia.is_check():
        return "Con esta jugada das jaque al rey rival."
    if pieza.piece_type == chess.PAWN and chess.square_file(jugada.to_square) in (3, 4):
        return "Avanzar un peón central ayuda a controlar casillas importantes del tablero."
    if pieza.piece_type in (chess.KNIGHT, chess.BISHOP) and tablero.fullmove_number <= 10:
        return "Desarrollar piezas al principio permite controlar más casillas y preparar ataques."
    if pieza.piece_type == chess.KING:
        return "Mueve tu rey con cuidado y comprueba que siga protegido."
    if pieza.piece_type == chess.ROOK:
        return "Activa la torre para que participe en la defensa y en las amenazas."
    return "Observa las casillas que controla la pieza después de moverla y la respuesta rival."


def texto_sugerencia(tablero: chess.Board, jugada: chess.Move) -> tuple[str, str, str]:
    """Devuelve pieza/color, coordenadas y notación en el mismo estado de juego."""
    pieza = tablero.piece_at(jugada.from_square)
    if pieza is None or jugada not in tablero.legal_moves:
        raise ValueError("La sugerencia debe ser una jugada legal de esta posición.")
    color = "blanco" if pieza.color == chess.WHITE else "negro"
    nombre = NOMBRE_PIEZA[pieza.piece_type]
    if jugada.promotion:
        nombre += " (promociona a " + NOMBRE_PIEZA[jugada.promotion] + ")"
    origen = chess.square_name(jugada.from_square).upper()
    destino = chess.square_name(jugada.to_square).upper()
    return f"Mueve el {nombre} {color}", f"{origen}  →  {destino}", tablero.san(jugada)


class AjedrezVisual:
    def _cargar_sprites(self) -> dict:
        """Load anti-aliased pieces bundled with the project (no font dependency)."""
        nombres = {chess.KING: "rey", chess.QUEEN: "dama", chess.ROOK: "torre",
                   chess.BISHOP: "alfil", chess.KNIGHT: "caballo", chess.PAWN: "peon"}
        imagenes = {}
        for color in (chess.WHITE, chess.BLACK):
            for tipo, nombre in nombres.items():
                archivo = ASSETS / f"{nombre}_{'blancas' if color else 'negras'}.png"
                if archivo.exists():
                    try:
                        imagenes[(color,tipo)] = Image.open(archivo).convert("RGBA")
                    except OSError:
                        pass
        return imagenes

    def _sprite(self, pieza: chess.Piece, size: int):
        clave = (pieza.color, pieza.piece_type, size)
        if clave not in self._sprite_cache:
            im = self._sprites.get((pieza.color,pieza.piece_type))
            if im is None:
                return None
            self._sprite_cache[clave] = ImageTk.PhotoImage(
                im.resize((size,size), Image.Resampling.LANCZOS), master=self.raiz)
        return self._sprite_cache[clave]

    def _imagen_tablero(self, size: int):
        """A subtle, deterministic grain makes the board feel like a premium physical set."""
        clave=(self.tema,size)
        if clave in self._tablero_cache:
            return self._tablero_cache[clave]
        from PIL import ImageColor
        canvas=Image.new("RGB",(size*8,size*8))
        draw=ImageDraw.Draw(canvas)
        light=ImageColor.getrgb(COLORES["casilla_clara"])
        dark=ImageColor.getrgb(COLORES["casilla_oscura"])
        for f in range(8):
            for c in range(8):
                x=c*size; y=f*size
                src = light if (c+f)%2==0 else dark
                draw.rectangle((x,y,x+size,y+size),fill=src)
                # Fine lines run through each square; keep text and pieces legible.
                rng=random.Random(f*47+c*73+1)
                for _ in range(max(3,size//7)):
                    yy=y+rng.randint(1,max(1,size-2))
                    diff=rng.choice((-6,-4,-3,3,4,6))
                    col=tuple(max(0,min(255,v+diff)) for v in src)
                    draw.line((x+2,yy,x+size-2,yy), fill=col, width=1)
                draw.line((x,y,x+size-1,y), fill=tuple(min(255,v+7) for v in src),width=1)
                draw.line((x,y,x,y+size-1), fill=tuple(min(255,v+7) for v in src),width=1)
        img=ImageTk.PhotoImage(canvas,master=self.raiz)
        self._tablero_cache={clave:img}
        return img

    def __init__(self, raiz: tk.Tk) -> None:
        self.raiz = raiz
        self.raiz.title("GRAN MAESTRO V7  |  Ajedrez inteligente")
        self.raiz.geometry("1370x890")
        self.raiz.minsize(1050, 720)
        self.raiz.configure(bg=COLORES["fondo"])

        self.partida = chess.Board()
        self.seleccion: chess.Square | None = None
        self.movimientos_san: list[str] = []
        self.modo = "Contra Stockfish"
        self.nivel = "Medio"
        self.ruta_stockfish = encontrar_stockfish()
        self.pensando = False
        self.cerrando = False
        self.numero_partida = 0
        self.cola_ia: queue.Queue = queue.Queue()
        self.cola_pistas: queue.Queue = queue.Queue()
        self.version_pista = 0
        self.calculando_pista = False
        self.pista: chess.Move | None = None
        self.fuente_pista = ""
        self.pulso = False
        self.feedback = "Selecciona una pieza. Stockfish puede enseñarte la próxima jugada."
        self.aprendizaje = tk.BooleanVar(value=True)
        self.tema = "Ébano y oro"
        self._sprites = self._cargar_sprites()
        self._sprite_cache = {}
        self._tablero_cache = {}
        self._cargar_configuracion()

        self._crear_interfaz()
        self._dibujar()
        self._solicitar_pista()
        self.raiz.after(520, self._animar_luces)
        self.raiz.bind("<Control-z>", lambda _e: self.deshacer())
        self.raiz.bind("<Control-n>", lambda _e: self.nueva_partida())
        self.raiz.bind("<Escape>", self._cancelar_seleccion)
        self.raiz.protocol("WM_DELETE_WINDOW", self._cerrar)

    def _etiqueta(self, padre, texto, tam=10, color=None, negrita=False, **opciones):
        return tk.Label(
            padre, text=texto, bg=opciones.pop("bg", COLORES["panel"]),
            fg=color or COLORES["blanco"],
            font=("Segoe UI", tam, "bold" if negrita else "normal"),
            justify="left", anchor="w", **opciones,
        )

    def _boton(self, padre, texto, accion, principal=False, ancho=None, compacto=False):
        boton = tk.Button(
            padre, text=texto, command=accion,
            bg=COLORES["acento"] if principal else COLORES["panel_2"],
            fg=COLORES["texto_boton"] if principal else COLORES["blanco"],
            activebackground=COLORES["principal_hover"] if principal else COLORES["boton_hover"],
            activeforeground=COLORES["texto_boton"] if principal else COLORES["blanco"],
            bd=0, relief="flat", cursor="hand2", padx=10 if compacto else 14, pady=6 if compacto else 10,
            font=("Segoe UI", 10, "bold"), highlightthickness=0,
            **({"width": ancho} if ancho else {}),
        )
        normal = COLORES["acento"] if principal else COLORES["panel_2"]
        hover = COLORES["principal_hover"] if principal else COLORES["boton_hover"]
        boton.bind("<Enter>", lambda _e: boton.configure(bg=hover))
        boton.bind("<Leave>", lambda _e: boton.configure(bg=normal))
        return boton

    def _seccion(self, padre, titulo, detalle=""):
        tarjeta_borde = tk.Frame(padre, bg=COLORES["borde"], padx=1, pady=1)
        tarjeta_borde.pack(fill="x", pady=(0, 11))
        tarjeta = tk.Frame(tarjeta_borde, bg=COLORES["panel"], padx=17, pady=14)
        tarjeta.pack(fill="both", expand=True)
        cabecera = tk.Frame(tarjeta, bg=COLORES["panel"])
        cabecera.pack(fill="x")
        self._etiqueta(cabecera, titulo, 11, COLORES["blanco"], True).pack(side="left")
        if detalle:
            self._etiqueta(cabecera, detalle, 9, COLORES["muted"]).pack(side="right")
        linea = tk.Frame(tarjeta, bg=COLORES["borde"], height=1)
        linea.pack(fill="x", pady=(10, 11))
        return tarjeta

    def _crear_interfaz(self) -> None:
        # Visualización V6: tablero expansible y un único panel lateral compacto.
        if hasattr(self, "marco_vista"):
            self.marco_vista.destroy()
        self.raiz.configure(bg=COLORES["fondo"])
        self.marco_vista = tk.Frame(self.raiz, bg=COLORES["fondo"])
        self.marco_vista.pack(fill="both", expand=True)

        cab = tk.Frame(self.marco_vista, bg=COLORES["cabecera"], height=80)
        cab.pack(fill="x")
        cab.pack_propagate(False)
        marca = tk.Frame(cab, bg=COLORES["acento"], padx=12, pady=7)
        marca.pack(side="left", padx=(18, 11), pady=12)
        tk.Label(marca, text="♞", font=("Segoe UI Symbol", 27),
                 bg=COLORES["acento"], fg=COLORES["texto_boton"]).pack()
        cab_texto = tk.Frame(cab, bg=COLORES["cabecera"])
        cab_texto.pack(side="left", pady=13)
        self._etiqueta(cab_texto, "GRAN MAESTRO", 18, negrita=True,
                       bg=COLORES["cabecera"]).pack(anchor="w")
        self._etiqueta(cab_texto, "ACADEMIA DE AJEDREZ    /    STOCKFISH", 9,
                       COLORES["acento"], bg=COLORES["cabecera"]).pack(anchor="w")

        controls = tk.Frame(cab, bg=COLORES["cabecera"])
        controls.pack(side="right", padx=18)
        # Only TWO modes. The engine used by BOTH is always Stockfish.
        self.combo_modo = ttk.Combobox(
            controls, state="readonly", width=18, font=("Segoe UI", 10),
            values=("Contra Stockfish", "Dos jugadores"), style="Ajedrez.TCombobox")
        self.combo_modo.set(self.modo)
        self.combo_modo.pack(side="left", padx=(0, 8))
        self.combo_modo.bind("<<ComboboxSelected>>", self._cambiar_modo)
        self.combo_nivel = ttk.Combobox(
            controls, state="readonly", width=9, font=("Segoe UI", 10),
            values=("Fácil", "Medio", "Difícil"), style="Ajedrez.TCombobox")
        self.combo_nivel.set(self.nivel)
        self.combo_nivel.pack(side="left", padx=(0, 8))
        self.combo_nivel.bind("<<ComboboxSelected>>", self._cambiar_dificultad)
        self._boton(controls, "↶ Deshacer", self.deshacer, compacto=True).pack(side="left", padx=(0, 6))
        self._boton(controls, "+ Nueva partida", self.nueva_partida, True, compacto=True).pack(side="left")
        tk.Frame(self.marco_vista, bg=COLORES["board_trim"], height=1).pack(fill="x")

        # Use native TCombobox with legible text on Windows / Tk 8.6.
        estilo = ttk.Style(self.raiz)
        estilo.configure("Ajedrez.TCombobox", fieldbackground="#f2e9dd",
                          background="#e5d0ab", foreground="#211b17",
                          borderwidth=0, padding=5)
        estilo.map("Ajedrez.TCombobox",
                   fieldbackground=[("readonly", "#f2e9dd")],
                   foreground=[("readonly", "#211b17")],
                   selectbackground=[("readonly", "#f2e9dd")],
                   selectforeground=[("readonly", "#211b17")])

        cuerpo = tk.Frame(self.marco_vista, bg=COLORES["fondo"])
        cuerpo.pack(fill="both", expand=True, padx=16, pady=(14, 10))

        tablero_zona = tk.Frame(cuerpo, bg=COLORES["panel"])
        tablero_zona.pack(side="left", fill="both", expand=True, padx=(0, 14))
        arriba = tk.Frame(tablero_zona, bg=COLORES["panel"], height=38)
        arriba.pack(fill="x", padx=15, pady=(9, 0))
        self._etiqueta(arriba, "♚  PIEZAS NEGRAS", 10, negrita=True).pack(side="left")
        self.estado = self._etiqueta(arriba, "Partida en curso", 9, COLORES["muted"])
        self.estado.pack(side="right")

        self.lienzo = tk.Canvas(tablero_zona, bg=COLORES["panel"],
                                borderwidth=0, highlightthickness=0, cursor="hand2")
        self.lienzo.pack(fill="both", expand=True, padx=10, pady=4)
        self.lienzo.bind("<Button-1>", self._clic_tablero)
        self.lienzo.bind("<Configure>", self._redimensionar_tablero)
        self.casilla = TAM_CASILLA
        self.origen_x = 0
        self.origen_y = 0

        pie_tablero = tk.Frame(tablero_zona, bg=COLORES["panel"], height=56)
        pie_tablero.pack(fill="x", padx=17, pady=(0, 10))
        self.etiqueta_turno = self._etiqueta(
            pie_tablero, "● TURNO: BLANCAS", 12, COLORES["acento"], True)
        self.etiqueta_turno.pack(anchor="w")
        self.etiqueta_feedback = self._etiqueta(
            pie_tablero, "Selecciona una pieza para comenzar", 9,
            COLORES["muted"], wraplength=680)
        self.etiqueta_feedback.pack(anchor="w", pady=(2, 0))

        # Single compact column. No 1/4, 2/4, 3/4 cards or scroll maze.
        derecha = tk.Frame(cuerpo, bg=COLORES["panel"], width=342)
        derecha.pack(side="right", fill="y")
        derecha.pack_propagate(False)
        lateral = tk.Frame(derecha, bg=COLORES["panel"], padx=18, pady=16)
        lateral.pack(fill="both", expand=True)
        self._etiqueta(lateral, "✧  ENTRENADOR STOCKFISH", 13,
                       COLORES["blanco"], True).pack(anchor="w")
        motor_linea = tk.Frame(lateral, bg=COLORES["panel"])
        motor_linea.pack(fill="x", pady=(8, 4))
        self.etiqueta_motor = self._etiqueta(motor_linea, "", 9,
                                             COLORES["acento"], True,
                                             wraplength=195)
        self.etiqueta_motor.pack(side="left", fill="x", expand=True)
        self._boton(motor_linea, "⚙ Motor", self._elegir_stockfish,
                    compacto=True).pack(side="right")
        self._actualizar_etiqueta_motor()

        activar = tk.Frame(lateral, bg=COLORES["panel"])
        activar.pack(fill="x", pady=(12, 10))
        self._etiqueta(activar, "APRENDIZAJE CON LUCES", 9,
                       COLORES["muted"], True).pack(side="left")
        tk.Checkbutton(activar, text="Activada", variable=self.aprendizaje,
                       command=self._alternar_aprendizaje,
                       bg=COLORES["panel"], fg=COLORES["acento"],
                       activebackground=COLORES["panel"], activeforeground=COLORES["acento"],
                       selectcolor=COLORES["panel_2"],
                       font=("Segoe UI", 9, "bold"), bd=0,
                       cursor="hand2").pack(side="right")
        card = tk.Frame(lateral, bg=COLORES["cabecera"], padx=14, pady=13)
        card.pack(fill="x")
        self.pista_estado = self._etiqueta(card, "STOCKFISH ANALIZA…", 9,
                                            COLORES["acento"], True,
                                            bg=COLORES["cabecera"])
        self.pista_estado.pack(anchor="w")
        self.pista_coordenadas = self._etiqueta(card, "— → —", 26,
                                                COLORES["blanco"], True,
                                                bg=COLORES["cabecera"])
        self.pista_coordenadas.pack(anchor="w", pady=(4, 4))
        self.pista_pieza = self._etiqueta(card, "Mueve la pieza indicada", 10,
                                          COLORES["blanco"], True,
                                          bg=COLORES["cabecera"], wraplength=270)
        self.pista_pieza.pack(anchor="w")
        self.pista_razon = self._etiqueta(lateral,
                                         "Amarillo: origen. Verde: destino.",
                                         10, COLORES["muted"], wraplength=291)
        self.pista_razon.pack(anchor="w", pady=(12, 4))
        self.pista_fuente = self._etiqueta(lateral, "", 8, COLORES["acento"],
                                          wraplength=290)
        self.pista_fuente.pack(anchor="w")
        botones_pista = tk.Frame(lateral, bg=COLORES["panel"])
        botones_pista.pack(fill="x", pady=(11, 15))
        self._boton(botones_pista, "✦ Ver mejor jugada", self._pedir_pista,
                    principal=True, compacto=True).pack(side="left", fill="x", expand=True)
        self._boton(botones_pista, "Ocultar", self._ocultar_pista,
                    compacto=True).pack(side="left", padx=(6, 0))
        tk.Frame(lateral, bg=COLORES["borde"], height=1).pack(fill="x", pady=(0, 13))
        self._etiqueta(lateral, "MOVIMIENTOS", 10,
                       COLORES["blanco"], True).pack(anchor="w", pady=(0, 8))
        hist_caja = tk.Frame(lateral, bg=COLORES["panel_2"])
        hist_caja.pack(fill="both", expand=True)
        self.historial = tk.Listbox(hist_caja, bg=COLORES["panel_2"],
                                    fg=COLORES["blanco"],
                                    font=("Consolas", 11),
                                    relief="flat", bd=0, highlightthickness=0,
                                    selectbackground=COLORES["resalte"], activestyle="none")
        self.historial.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=7)
        barra_hist = tk.Scrollbar(hist_caja, command=self.historial.yview,
                                  bg=COLORES["panel_2"], width=11)
        barra_hist.pack(side="right", fill="y")
        self.historial.configure(yscrollcommand=barra_hist.set)
        paleta = tk.Frame(lateral, bg=COLORES["panel"])
        paleta.pack(fill="x", pady=(12, 0))
        self._etiqueta(paleta, "ESTILO", 9, COLORES["muted"], True).pack(side="left")
        self.combo_tema = ttk.Combobox(paleta, state="readonly", width=18,
                                       values=list(TEMAS),
                                       style="Ajedrez.TCombobox", font=("Segoe UI", 9))
        self.combo_tema.set(self.tema)
        self.combo_tema.pack(side="right")
        self.combo_tema.bind("<<ComboboxSelected>>", self._cambiar_tema)

        footer = tk.Frame(self.marco_vista, bg=COLORES["cabecera"], height=32)
        footer.pack(fill="x")
        self._etiqueta(footer,
                       "  ♟  GRAN MAESTRO  /  Club de ajedrez   ·   Clic para mover   ·   Amarillo: pieza   ·   Verde: destino   ·   Ctrl+Z: deshacer",
                       9, COLORES["muted"], bg=COLORES["cabecera"]).pack(side="left", padx=10, pady=7)

    def _redimensionar_tablero(self, evento=None) -> None:
        # Redraw only when the effective square or board position changes.
        w = max(1, self.lienzo.winfo_width())
        h = max(1, self.lienzo.winfo_height())
        size = max(36, min((w - 16) // 8, (h - 16) // 8))
        ox = (w - 8 * size) // 2
        oy = (h - 8 * size) // 2
        if (self.casilla, self.origen_x, self.origen_y) != (size, ox, oy):
            self.casilla, self.origen_x, self.origen_y = size, ox, oy
            self._dibujar()

    def _cambiar_tema(self, _evento=None) -> None:
        nuevo = self.combo_tema.get()
        if nuevo not in TEMAS or nuevo == self.tema:
            return
        self.tema = nuevo
        self._tablero_cache.clear()
        self._sprite_cache.clear()
        COLORES.clear()
        COLORES.update(TEMAS[nuevo])
        self._guardar_configuracion()
        self._crear_interfaz()
        self._dibujar()

    def _centro(self, casilla: int) -> tuple[float, float]:
        s = self.casilla
        return (self.origen_x + (chess.square_file(casilla) + .5) * s,
                self.origen_y + (7 - chess.square_rank(casilla) + .5) * s)

    def _dibujar(self) -> None:
        if not hasattr(self, "lienzo"):
            return
        self.lienzo.delete("all")
        s, ox, oy = self.casilla, self.origen_x, self.origen_y
        pad=11
        # Deep outer frame and two satin-gold hairline borders.
        self.lienzo.create_rectangle(ox-pad-5,oy-pad-5,ox+8*s+pad+5,oy+8*s+pad+5,
                                     fill=COLORES["board_glow"],outline="")
        self.lienzo.create_rectangle(ox-pad,oy-pad,ox+8*s+pad,oy+8*s+pad,
                                     fill=COLORES["board_outer"],outline=COLORES["board_trim"],width=2)
        self.lienzo.create_rectangle(ox-3,oy-3,ox+8*s+3,oy+8*s+3,
                                     fill=COLORES["board_trim"],outline="")
        self.lienzo.create_image(ox,oy,anchor="nw",image=self._imagen_tablero(s))
        ultimo = self.partida.peek() if self.partida.move_stack else None
        jaque = self.partida.king(self.partida.turn) if self.partida.is_check() else None
        destinos=(set(m.to_square for m in self.partida.legal_moves
                       if m.from_square==self.seleccion)
                  if self.seleccion is not None else set())
        pista=(self.pista if self.aprendizaje.get() and
               self.pista in self.partida.legal_moves else None)
        for f in range(8):
            for c in range(8):
                sq=chess.square(c,7-f)
                x=ox+c*s; y=oy+f*s
                light=(f+c)%2==0
                if ultimo and sq in (ultimo.from_square,ultimo.to_square):
                    self.lienzo.create_rectangle(x+3,y+3,x+s-3,y+s-3,
                         fill=COLORES["ultimo"],stipple="gray50",outline="")
                if sq == jaque:
                    self.lienzo.create_rectangle(x+3,y+3,x+s-3,y+s-3,
                         outline=COLORES["jaque"],width=4)
                if sq==self.seleccion:
                    self.lienzo.create_rectangle(x+3,y+3,x+s-3,y+s-3,
                         outline=COLORES["seleccion"],width=4)
                if sq in destinos:
                    if self.partida.piece_at(sq):
                        self.lienzo.create_oval(x+6,y+6,x+s-6,y+s-6,
                                               outline=COLORES["luz_destino"],width=3)
                    else:
                        r=s*.12
                        self.lienzo.create_oval(x+s/2-r,y+s/2-r,x+s/2+r,y+s/2+r,
                            fill=COLORES["luz_destino"],outline="")
                pieza=self.partida.piece_at(sq)
                if pieza:
                    sprite=self._sprite(pieza,max(16,int(s*.94)))
                    if sprite is not None:
                        self.lienzo.create_image(x+s/2,y+s/2,image=sprite)
                    else:
                        glifo=PIEZAS[pieza.color][pieza.piece_type]
                        color_pieza="#fffdf6" if pieza.color else "#1c1817"
                        self.lienzo.create_text(x+s/2,y+s/2,text=glifo,fill=color_pieza,
                             font=("Segoe UI Symbol",max(27,int(s*.80))))
                coordcol=COLORES["texto_boton"] if light else COLORES["blanco"]
                if c==0:
                    self.lienzo.create_text(x+9,y+11,text=str(8-f),
                           font=("Segoe UI",max(8,int(s*.14)),"bold"),fill=coordcol)
                if f==7:
                    self.lienzo.create_text(x+s-10,y+s-10,text="abcdefgh"[c],
                           font=("Segoe UI",max(8,int(s*.14)),"bold"),fill=coordcol)
        if pista:
            # In-game LEDs are a purely visual preview of later GPIO LEDs.
            for square, color in ((pista.from_square,COLORES["luz_origen"]),
                                  (pista.to_square,COLORES["luz_destino"])):
                x,y=self._centro(square)
                self.lienzo.create_rectangle(x-s/2+3,y-s/2+3,x+s/2-3,y+s/2-3,
                      outline=color,width=5 if self.pulso else 3)
                r=max(6,int(s*.12))
                self.lienzo.create_oval(x+s/2-2*r,y-s/2+4,x+s/2-2,y-s/2+4+2*r,
                       fill=color,outline=COLORES["board_outer"],width=2)
        self._actualizar_panel()

    def _animar_luces(self) -> None:
        if self.cerrando:
            return
        self.pulso = not self.pulso
        if self.pista is not None and self.aprendizaje.get():
            self._dibujar()
        self.raiz.after(520, self._animar_luces)

    def _actualizar_panel(self) -> None:
        resultado = self.partida.outcome(claim_draw=True)
        if resultado:
            titulo = ("TABLAS" if resultado.winner is None else
                      "GANAN BLANCAS" if resultado.winner == chess.WHITE else "GANAN NEGRAS")
            detalle = "Partida terminada"
        elif self.pensando:
            titulo, detalle = "● TURNO: NEGRAS", "Stockfish está pensando..."
        else:
            titulo = "● TURNO: BLANCAS" if self.partida.turn == chess.WHITE else "● TURNO: NEGRAS"
            detalle = "¡Jaque!" if self.partida.is_check() else "Partida en curso"
        self.etiqueta_turno.config(text=titulo)
        self.estado.config(text=detalle)
        self.etiqueta_feedback.config(text=self.feedback)
        self.historial.delete(0, tk.END)
        for i in range(0, len(self.movimientos_san), 2):
            blancas = self.movimientos_san[i]
            negras = self.movimientos_san[i + 1] if i + 1 < len(self.movimientos_san) else ""
            self.historial.insert(tk.END, f"{i // 2 + 1:>2}.  {blancas:<9} {negras}")
        if self.movimientos_san:
            self.historial.yview_moveto(1.0)
        self._actualizar_pista_panel()

    def _actualizar_pista_panel(self) -> None:
        if not self.aprendizaje.get():
            estado, coords, pieza = "APRENDIZAJE DESACTIVADO", "—   →   —", "Activa Aprendizaje para recibir indicaciones"
            razon, fuente = "Puedes seguir jugando normalmente.", ""
        elif self.partida.is_game_over(claim_draw=True):
            estado, coords, pieza = "PARTIDA FINALIZADA", "—   →   —", "¡Buen trabajo!"
            razon, fuente = "Inicia otra partida para continuar practicando.", ""
        elif self.modo != "Dos jugadores" and self.partida.turn == chess.BLACK:
            estado, coords, pieza = "TURNO DE STOCKFISH", "—   →   —", "Stockfish prepara su respuesta"
            razon, fuente = "Las pistas se mostrarán cuando vuelvas a jugar con blancas.", ""
        elif self.pista and self.pista in self.partida.legal_moves:
            pieza, coords, san = texto_sugerencia(self.partida, self.pista)
            color = "BLANCAS" if self.partida.turn == chess.WHITE else "NEGRAS"
            estado = f"● LUCES ENCENDIDAS · {color}"
            razon = explicar_sugerencia(self.partida, self.pista)
            fuente = f"Notación: {san}  |  Motor: {self.fuente_pista}  |  Pista opcional"
        elif not self.ruta_stockfish or not Path(self.ruta_stockfish).is_file():
            estado, coords, pieza = "CONFIGURA STOCKFISH", "—   →   —", "Pulsa «⚙ Motor» y selecciona Stockfish"
            razon, fuente = "Stockfish enseñará jugadas con luces y coordenadas.", "No se usan pistas de otro motor."
        elif self.calculando_pista:
            estado, coords, pieza = "ANALIZANDO POSICIÓN…", "—   →   —", "Buscando la mejor jugada"
            razon, fuente = "En breve se encenderán dos casillas del tablero.", ""
        else:
            estado, coords, pieza = "LISTO PARA APRENDER", "—   →   —", "Pulsa «Recomendar jugada»"
            razon, fuente = "Amarillo = pieza que debes mover. Verde = a dónde moverla.", ""
        self.pista_estado.config(text=estado)
        self.pista_coordenadas.config(text=coords)
        self.pista_pieza.config(text=pieza)
        self.pista_razon.config(text=razon)
        self.pista_fuente.config(text=fuente)

    def _clic_tablero(self, evento: tk.Event) -> None:
        if self.pensando or (self.modo != "Dos jugadores" and self.partida.turn == chess.BLACK):
            return
        if self.partida.is_game_over(claim_draw=True):
            return
        columna = (evento.x - self.origen_x) // self.casilla
        fila = (evento.y - self.origen_y) // self.casilla
        if not (0 <= fila < 8 and 0 <= columna < 8):
            return
        casilla = chess.square(columna, 7 - fila)
        pieza = self.partida.piece_at(casilla)
        if self.seleccion == casilla:
            self.seleccion = None
        elif pieza and pieza.color == self.partida.turn:
            self.seleccion = casilla
        elif self.seleccion is not None:
            candidatas = [
                mov for mov in self.partida.legal_moves
                if mov.from_square == self.seleccion and mov.to_square == casilla
            ]
            if candidatas:
                if len(candidatas) > 1:
                    self._elegir_promocion(candidatas)
                    return
                self._hacer_movimiento(candidatas[0])
                return
            self.seleccion = None
        self._dibujar()

    def _elegir_promocion(self, candidatas: list[chess.Move]) -> None:
        ventana = tk.Toplevel(self.raiz)
        ventana.title("Promoción de peón")
        ventana.configure(bg=COLORES["panel"])
        ventana.transient(self.raiz)
        ventana.grab_set()
        ventana.resizable(False, False)
        ventana.protocol("WM_DELETE_WINDOW", lambda: (ventana.destroy(), self._cancelar_seleccion()))
        self._etiqueta(ventana, "Elige la pieza de promoción", 13, negrita=True).pack(padx=20, pady=(20, 12))
        botones = tk.Frame(ventana, bg=COLORES["panel"])
        botones.pack(padx=15, pady=(0, 20))
        for tipo, nombre in ((chess.QUEEN, "Dama"), (chess.ROOK, "Torre"),
                             (chess.BISHOP, "Alfil"), (chess.KNIGHT, "Caballo")):
            mov = next((m for m in candidatas if m.promotion == tipo), None)
            if mov is not None:
                self._boton(
                    botones, nombre, lambda jugada=mov: (ventana.destroy(), self._hacer_movimiento(jugada))
                ).pack(side="left", padx=3)

    def _hacer_movimiento(self, jugada: chess.Move) -> None:
        if jugada not in self.partida.legal_moves:
            messagebox.showwarning("Jugada no válida", "Esa jugada no está permitida.")
            return
        seguir_pista = self.aprendizaje.get() and self.pista == jugada
        quien = "Stockfish" if self.modo != "Dos jugadores" and self.partida.turn == chess.BLACK else "Jugador"
        nombre_san = self.partida.san(jugada)
        self.movimientos_san.append(nombre_san)
        self.partida.push(jugada)
        self.seleccion = None
        self.feedback = (
            f"¡Excelente! Seguiste la pista: {nombre_san}." if seguir_pista else
            f"{quien}: {nombre_san}. Movimiento registrado correctamente."
        )
        self._invalidar_pista()
        if self.modo != "Dos jugadores" and self.partida.turn == chess.BLACK:
            self._iniciar_ia()
        else:
            self._dibujar()
            self._solicitar_pista()

    def _invalidar_pista(self) -> None:
        self.version_pista += 1
        self.pista = None
        self.calculando_pista = False
        self.fuente_pista = ""

    def _solicitar_pista(self) -> None:
        self._invalidar_pista()
        if self.cerrando or not self.aprendizaje.get() or self.partida.is_game_over(claim_draw=True):
            self._dibujar()
            return
        # Stockfish enseña a ambos jugadores humanos; cuando él juega, no muestra pistas.
        if self.modo != "Dos jugadores" and self.partida.turn == chess.BLACK:
            self._dibujar()
            return
        if not self.ruta_stockfish or not Path(self.ruta_stockfish).is_file():
            self.feedback = "Selecciona el ejecutable de Stockfish para activar el maestro."
            self._dibujar()
            return
        self.calculando_pista = True
        id_solicitud = self.version_pista
        copia = self.partida.copy(stack=False)
        ruta = self.ruta_stockfish
        self._dibujar()

        def calcular() -> None:
            try:
                motor = chess.engine.SimpleEngine.popen_uci(ruta, timeout=10)
                try:
                    # Entrenador siempre fuerte: independiente del nivel del rival.
                    resultado = motor.play(copia, chess.engine.Limit(time=0.45))
                    jugada = resultado.move
                finally:
                    motor.quit()
                self.cola_pistas.put((id_solicitud, jugada, "Stockfish", ""))
            except Exception as error:
                self.cola_pistas.put((id_solicitud, None, "", str(error)))

        threading.Thread(target=calcular, daemon=True).start()
        self.raiz.after(90, self._revisar_pistas)

    def _revisar_pistas(self) -> None:
        if self.cerrando:
            return
        while True:
            try:
                id_solicitud, sugerencia, fuente, error = self.cola_pistas.get_nowait()
            except queue.Empty:
                break
            if id_solicitud != self.version_pista or not self.calculando_pista:
                continue
            self.calculando_pista = False
            if sugerencia and sugerencia in self.partida.legal_moves:
                self.pista = sugerencia
                self.fuente_pista = fuente
            else:
                self.feedback = "Stockfish no pudo analizar: " + (error or "movimiento inválido")
            self._dibujar()
        if self.calculando_pista:
            self.raiz.after(90, self._revisar_pistas)

    def _alternar_aprendizaje(self) -> None:
        if self.aprendizaje.get():
            self.feedback = "Aprendizaje activo: sigue las dos casillas iluminadas."
            self._solicitar_pista()
        else:
            self.feedback = "Aprendizaje desactivado. Puedes jugar libremente."
            self._invalidar_pista()
            self._dibujar()

    def _pedir_pista(self) -> None:
        if not self.aprendizaje.get():
            self.aprendizaje.set(True)
        self._solicitar_pista()

    def _ocultar_pista(self) -> None:
        self.aprendizaje.set(False)
        self._alternar_aprendizaje()

    def deshacer(self) -> None:
        if not self.partida.move_stack:
            return
        # Si respondió la computadora: deshacer dos; si aún pensaba: una.
        cantidad = (2 if self.modo != "Dos jugadores" and
                    self.partida.turn == chess.WHITE and not self.pensando else 1)
        self.numero_partida += 1
        self.pensando = False
        for _ in range(min(cantidad, len(self.partida.move_stack))):
            self.partida.pop()
            self.movimientos_san.pop()
        self.seleccion = None
        self.feedback = "Movimiento deshecho. Puedes volver a intentarlo."
        self._dibujar()
        self._solicitar_pista()

    def _cargar_configuracion(self) -> None:
        try:
            if CONFIG.exists():
                datos = json.loads(CONFIG.read_text(encoding="utf-8"))
                guardado = datos.get("tema", "Ébano y oro")
                guardado = {"Madera clásica": "Ébano y oro", "Blanco y negro": "Pizarra moderna"}.get(guardado, guardado)
                if guardado in TEMAS:
                    self.tema = guardado
                    COLORES.clear()
                    COLORES.update(TEMAS[guardado])
                ruta = datos.get("stockfish", "")
                if isinstance(ruta, str) and Path(ruta).is_file():
                    self.ruta_stockfish = ruta
                if datos.get("modo") in ("Contra Stockfish", "Dos jugadores"):
                    self.modo = datos["modo"]
                if datos.get("nivel") in ("Fácil", "Medio", "Difícil"):
                    self.nivel = datos["nivel"]
        except (OSError, ValueError, TypeError):
            pass

    def _guardar_configuracion(self) -> None:
        try:
            CONFIG.write_text(json.dumps({"stockfish": self.ruta_stockfish, "tema": self.tema,
                                          "modo": self.modo, "nivel": self.nivel}, indent=2),
                              encoding="utf-8")
        except OSError:
            pass

    def _actualizar_etiqueta_motor(self) -> None:
        texto = ("●  MOTOR CONECTADO"
                 if self.ruta_stockfish and Path(self.ruta_stockfish).is_file()
                 else "○  CONECTAR MOTOR")
        self.etiqueta_motor.config(text=texto)

    def _elegir_stockfish(self) -> None:
        archivo = filedialog.askopenfilename(
            parent=self.raiz, title="Seleccionar motor Stockfish",
            filetypes=[("Ejecutables", "*.exe"), ("Todos los archivos", "*.*")],
        )
        if archivo:
            self.ruta_stockfish = archivo
            self._guardar_configuracion()
            self._actualizar_etiqueta_motor()
            self.feedback = "Motor seleccionado: Stockfish enseñará y jugará como rival."
            self._solicitar_pista()
            if self.modo == "Contra Stockfish" and self.partida.turn == chess.BLACK:
                self._iniciar_ia()

    def _cambiar_modo(self, _evento=None) -> None:
        nuevo = self.combo_modo.get()
        if nuevo == self.modo:
            return
        if nuevo == "Contra Stockfish" and (not self.ruta_stockfish or not Path(self.ruta_stockfish).is_file()):
            messagebox.showwarning(
                "Configura Stockfish", "Primero pulsa «⚙ Motor» y selecciona "
                "stockfish-windows-x86-64-universal.exe.",
            )
            self.combo_modo.set(self.modo)
            return
        if self.partida.move_stack and not messagebox.askyesno(
            "Cambiar modo", "El cambio reiniciará la partida actual. ¿Continuar?"
        ):
            self.combo_modo.set(self.modo)
            return
        self.modo = nuevo
        self._guardar_configuracion()
        self.nueva_partida(sin_preguntar=True)

    def _cambiar_dificultad(self, _evento=None) -> None:
        self.nivel = self.combo_nivel.get()
        self._guardar_configuracion()
        self._solicitar_pista()

    def _iniciar_ia(self) -> None:
        if (self.cerrando or self.pensando or self.modo == "Dos jugadores"
                or self.partida.turn != chess.BLACK
                or self.partida.is_game_over(claim_draw=True)):
            self._dibujar()
            return
        if not self.ruta_stockfish or not Path(self.ruta_stockfish).is_file():
            self.feedback = "Falta el ejecutable de Stockfish. Usa «⚙ Motor»."
            self._dibujar()
            return
        self.pensando = True
        self.numero_partida += 1
        id_turno = self.numero_partida
        copia = self.partida.copy(stack=True)
        modo, nivel, ruta = self.modo, self.nivel, self.ruta_stockfish
        self._dibujar()

        def trabajar() -> None:
            try:
                if not ruta or not Path(ruta).is_file():
                    raise FileNotFoundError("No se encuentra Stockfish. Configura la ruta del motor.")
                motor = chess.engine.SimpleEngine.popen_uci(ruta, timeout=10)
                try:
                    habilidad = {"Fácil": 0, "Medio": 9, "Difícil": 20}
                    if "Skill Level" in motor.options:
                        motor.configure({"Skill Level": habilidad[nivel]})
                    tiempo = {"Fácil": 0.15, "Medio": 0.5, "Difícil": 1.2}[nivel]
                    jugada = motor.play(copia, chess.engine.Limit(time=tiempo)).move
                finally:
                    motor.quit()
                self.cola_ia.put((id_turno, jugada, ""))
            except Exception as error:
                self.cola_ia.put((id_turno, None, str(error)))

        threading.Thread(target=trabajar, daemon=True).start()
        self.raiz.after(90, self._revisar_ia)

    def _revisar_ia(self) -> None:
        if self.cerrando:
            return
        while True:
            try:
                id_turno, jugada, error = self.cola_ia.get_nowait()
            except queue.Empty:
                break
            if id_turno != self.numero_partida or not self.pensando:
                continue
            self.pensando = False
            if error or jugada is None or jugada not in self.partida.legal_moves:
                messagebox.showerror("Stockfish", "El motor no pudo realizar su jugada.\n\n" +
                                     (error or "Jugada no válida."))
                self.feedback = "Revisa el archivo ejecutable de Stockfish."
                self._dibujar()
                return
            self._hacer_movimiento(jugada)
            return
        if self.pensando:
            self.raiz.after(90, self._revisar_ia)

    def nueva_partida(self, sin_preguntar: bool = False) -> None:
        if not sin_preguntar and self.partida.move_stack and not messagebox.askyesno(
            "Nueva partida", "¿Reiniciar el tablero y borrar los movimientos?"
        ):
            return
        self.numero_partida += 1
        self.pensando = False
        self.partida.reset()
        self.movimientos_san.clear()
        self.seleccion = None
        self.feedback = "Nueva partida. Stockfish puede sugerir la primera jugada."
        self._dibujar()
        self._solicitar_pista()

    def _cancelar_seleccion(self, _evento=None) -> None:
        self.seleccion = None
        self._dibujar()

    def _cerrar(self) -> None:
        self.cerrando = True
        self.numero_partida += 1
        self.version_pista += 1
        self.raiz.destroy()


def main() -> None:
    raiz = tk.Tk()
    AjedrezVisual(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
