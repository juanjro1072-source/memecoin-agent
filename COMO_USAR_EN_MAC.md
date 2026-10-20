# Cómo usar el observador en tu Mac

El observador mira memecoins **reales** de Solana y hace compras **imaginarias**
con dinero ficticio. No usa wallet, ni claves, ni dinero real: sólo lee datos
públicos de DexScreener y RugCheck.

Para cada decisión guarda el precio exacto de ese momento, y luego el precio
**1 hora** y **24 horas** después, para ver si acertó.

---

## Una sola vez: preparar el Mac

### 1. Abrir la Terminal

Pulsa `⌘ Cmd` + `Espacio`, escribe **Terminal** y pulsa Enter. Se abre una
ventana donde se escriben órdenes. Cada orden se escribe y se pulsa Enter.

### 2. Instalar Python (si hace falta)

Escribe:

```
python3 --version
```

- Si dice **3.11** o más (por ejemplo `Python 3.12.7`), salta al paso 3.
- Si dice 3.9, 3.10, o te ofrece instalar "herramientas de línea de comandos":
  1. Entra en https://www.python.org/downloads/ y descarga el instalador para macOS.
  2. Ábrelo y sigue los pasos (Continuar → Aceptar → Instalar).
  3. **Importante:** al terminar se abre una carpeta. Haz doble clic en
     **Install Certificates.command**. Sin esto, Python no puede conectarse
     a internet de forma segura.
  4. Cierra la Terminal, ábrela de nuevo y repite `python3 --version`.

### 3. Descargar el proyecto

1. Entra en tu repo en GitHub: https://github.com/juanjro1072-source/memecoin-agent
2. Arriba a la izquierda, en el botón que dice **main**, elige la rama
   **claude/happy-brahmagupta-qsqd4t**.
3. Botón verde **Code** → **Download ZIP**.
4. Abre el ZIP (doble clic). Mueve la carpeta a **Documentos** y cámbiale el
   nombre a `memecoin-agent`.

### 4. Entrar en la carpeta y comprobar que todo funciona

```
cd ~/Documents/memecoin-agent
python3 -m unittest discover -s tests -t .
```

Al final debe decir **OK**.

### 5. Probar la conexión con DexScreener y RugCheck

Con un token conocido de Solana (BONK):

```
python3 -m vivo probar DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263
```

Debe mostrar un precio de DexScreener y "lo que entendí" de RugCheck.
**Mándame lo que salga la primera vez**: desde la nube no pude probar estas
dos páginas, y así confirmo que el programa entiende bien sus datos.

---

## Cada día: arrancar y detener

### Arrancar

```
cd ~/Documents/memecoin-agent
caffeinate -i python3 -m vivo
```

- `caffeinate -i` evita que el Mac se duerma mientras el observador trabaja.
  Aun así, si cierras la tapa del portátil se dormirá: déjalo abierto y
  enchufado.
- Verás una línea por cada decisión, por ejemplo:
  `14:32  $CAPYX: 🟢 compra sombra $10.00 · hype 85, riesgo 0`
- Deja la ventana abierta. Puedes minimizarla.

### Detener (elige una)

- **Rápido:** en la ventana de la Terminal pulsa `Control` + `C`.
- **Interruptor de emergencia:** abre otra ventana de Terminal y escribe:

  ```
  touch ~/Documents/memecoin-agent/PARAR.txt
  ```

  El observador se detiene en pocos segundos y **no vuelve a arrancar
  mientras exista ese archivo**. Para quitarlo:

  ```
  rm ~/Documents/memecoin-agent/PARAR.txt
  ```

Al detenerlo no se pierde nada: la próxima vez que lo arranques sigue donde
iba y completa los precios de 1 hora y 24 horas que falten.

---

## Dónde ver los resultados

Todo queda en la carpeta `diario/vivo/` del proyecto:

| Archivo | Qué es |
|---|---|
| `resumen_AAAA-MM-DD.md` | **El resumen del día**: compras, rechazos, cómo iban a 1 h y 24 h, y totales. |
| `AAAA-MM-DD/` | Una autopsia por decisión: qué vio, qué decidió y qué resultó. |
| `sombra.db` | La memoria del observador. No la borres. |

Para abrir la carpeta desde la Terminal:

```
open ~/Documents/memecoin-agent/diario/vivo
```

Los `.md` se abren con TextEdit. Para rehacer el resumen de hoy sin arrancar
el observador: `python3 -m vivo resumen`.

Para empezar de cero (borra toda la historia): `rm -rf diario/vivo`.

---

## Si algo falla

| Mensaje | Qué hacer |
|---|---|
| `CERTIFICATE_VERIFY_FAILED` | Haz el paso 2.3: doble clic en **Install Certificates.command** (está en Aplicaciones → Python 3.x). |
| `Necesitas Python 3.11 o más nuevo` | Haz el paso 2. |
| `No module named vivo` | No estás en la carpeta del proyecto: `cd ~/Documents/memecoin-agent`. |
| `No pude hablar con DexScreener` | Sin internet o la página está caída. Sigue solo en el siguiente ciclo. |
| Todo sale "rechazada (seguridad)" con «falta el dato» | Mándame la salida de `python3 -m vivo probar …`: puede que RugCheck haya cambiado sus datos. |
| `medido con N min de retraso` | El Mac estuvo dormido. El dato vale, pero se tomó tarde. |
