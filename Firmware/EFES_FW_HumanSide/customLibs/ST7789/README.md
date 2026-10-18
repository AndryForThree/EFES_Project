# ST7789 per EFES

Tutte le funzioni di disegno sono asincrone e condividono il produttore
di blocchi RGB565. La configurazione SPI/DMA resta di competenza di CubeMX.

## File e responsabilità

- `st7789_config.h`: handle SPI, CS/DC, geometria, rotazione iniziale,
  inversione iniziale, dimensione dei buffer e timeout delle chiamate blocking.
- `st7789_transport.c/.h`: comandi e parametri blocking, transazione dei pixel,
  invio DMA e instradamento del completamento e degli errori HAL.
- `st7789.c`: inizializzazione e comandi del controller.
- `st7789_graphics.c/.h`: generatori di finestre e pixel, stato e double buffering.
  L'header è interno.
- `st7789.h`: API pubblica e colori.

Il progetto usa RESET collegato a nRST, pannello completo 240x320 in landscape,
RGB565 e SPI a 8 bit. SCK/MOSI sono quelli configurati da CubeMX per l'handle
scelto; CS/DC sono GPIO controllati dal trasporto. Il DMA TX deve essere normal,
memory-to-peripheral, byte/byte, con incremento memoria e periferica fissa.
La libreria verifica questa configurazione in `ST7789_Init()` e non contiene
un percorso alternativo senza DMA.

## Uso dal main

Chiamare Init dopo GPIO, DMA e SPI. Init è blocking, applica le attese iniziali
del controller, ma non avvia un riempimento. Per ogni operazione asincrona:

```c
/* Una sola volta, quando si vuole avviare il disegno. */
ST7789_Result result = ST7789_Fill_Color(RED);
/* OK: richiesta accettata. BUSY: operazione precedente ancora in corso. */

/* A ogni giro del main, insieme al resto dell'applicazione. */
ST7789_Process();
/* Quando GetState() torna IDLE si può avviare il disegno successivo. */
```

Non richiamare Fill ad ogni giro per lo stesso disegno: serve solo avviare
la richiesta una volta. Non attendere con HAL_Delay o con un ciclo vuoto
durante il disegno: bisogna continuare a chiamare Process.

Tutte le API di disegno restituiscono ST7789_Result, incluse quelle che prima
restituivano void. Fill e DrawRectangle usano coordinate finali inclusive;
DrawFilledRectangle usa larghezza/altezza in pixel e ritaglia ai bordi.
Le richieste restituite BUSY o INVALID_ARGUMENT non cambiano il disegno attivo.
L'applicazione decide se e quando riprovare; non esiste una coda interna.
Non concatenare chiamate Draw/Write senza attendere IDLE fra le richieste.
Le API registrano il lavoro; la finestra SPI viene impostata da Process.

## Finestre e generazione dei pixel

- Fill e immagini usano una finestra continua, suddivisa nei buffer disponibili.
- FillHorizontalGradient genera una sfumatura simmetrica a schermo intero:
  colore dei bordi -> colore centrale -> colore dei bordi. Le componenti RGB565
  sono interpolate separatamente e i pixel sono generati nei buffer esistenti.
- Rettangoli vuoti usano fino a quattro finestre, senza riscrivere gli angoli.
- Le linee usano Bresenham e raggruppano pixel consecutivi nella stessa riga
  o colonna. Una diagonale a 45 gradi ha necessariamente segmenti di un pixel.
- Triangoli vuoti sono tre linee; quelli pieni usano intersezioni per riga.
  Un triangolo pieno degenere viene ridotto al suo segmento più lungo.
- Cerchi pieni e circonferenze usano una finestra quadrata ritagliata allo schermo,
  con antialiasing tramite 4x4 campioni sui pixel di bordo. Entrambe le API
  ricevono `background` dopo `color`: l'intero riquadro viene ridisegnato su
  quello sfondo uniforme. La circonferenza ha spessore radiale di un pixel
  e cancella anche il disco interno con background. Raggio zero disegna un pixel.
- Il testo usa una finestra per riga, o una per campo a larghezza in pixel.
  I font sono proporzionali, selezionati tramite FontId dal registro Fonts.
  Misura e disegno condividono avanzamenti e offset dei glifi. Nessun kerning.
  WriteString gestisce newline e wrapping al bordo destro; MeasureText misura
  le sole righe esplicite, senza wrapping. WriteTextField allinea una singola
  riga a sinistra, al centro o a destra e riscrive tutto il campo, evitando
  residui del testo precedente. Una stringa troppo larga viene rifiutata.
  I caratteri sono a un byte, non UTF-8: usare 0xB0 per il grado. Caratteri non
  esportati restituiscono INVALID_ARGUMENT. Le bitmap dei glifi sono ritagliate,
  row-major a 4 bit di copertura, primo pixel nel nibble alto, righe allineate
  a byte. I pixel di testo vengono composti direttamente nel blocco DMA.
  Le sovrapposizioni conservano la copertura maggiore. Una palette di 16 RGB565
  combina testo e sfondo una volta per richiesta, senza blending per pixel.
- DrawSteeringWheel genera un volante a tre razze con riferimento colorato,
  includendo lo sfondo in una singola finestra quadrata. Gli angoli sono in
  decimi di grado, positivi in senso orario. Seno e coseno sono calcolati una
  volta all'avvio del disegno; i pixel usano poi aritmetica intera e i normali
  buffer DMA. Non serve un framebuffer aggiuntivo. Il quadrato deve stare
  interamente sul display e avere lato di almeno 16 pixel.

Cerchi e dischi vengono ritagliati ai bordi. Le estremità di linee e triangoli
devono essere sullo schermo; parametri non validi restituiscono INVALID_ARGUMENT.
DrawPixel_4px conserva l'impronta effettiva 3x3 dell'originale, nonostante il nome.
Non vengono riscritti lo sfondo o l'interno di una forma vuota.

Stringhe, font e immagini devono rimanere validi e invariati fino a IDLE:
non passare un array locale che esce dallo scope e non modificarlo nel frattempo.
WriteChar conserva internamente il singolo carattere. DrawImage mantiene il
formato byte dell'originale (dati già predisposti per l'invio SPI, byte alto per
primo in memoria), senza scambiare automaticamente i byte di un array uint16_t.
I colori delle primitive e del testo sono invece normali valori RGB565.

## Double buffering e interrupt

`ST7789_BUFFER_PIXELS` è il numero massimo di pixel per buffer. Sono sempre
due buffer: con 320 pixel ciascuno, i dati occupano 1280 byte di RAM, più i
metadati. Non è necessario che la dimensione coincida con una riga o divida
esattamente l'area: l'ultimo blocco può essere più corto. Ogni blocco RGB565
contiene il byte più significativo seguito da quello meno significativo.
Il limite di 32767 pixel garantisce al massimo 65534 byte per chiamata HAL;
la RAM disponibile impone in pratica un limite molto più basso.

Process prepara al massimo un blocco per chiamata, con interrupt abilitati.
Il buffer viene pubblicato come PRONTO soltanto dopo aver finito la scrittura.
Il DMA non legge mai un buffer ancora in preparazione. Le brevi sezioni
critiche proteggono lo scambio degli stati e l'avvio del DMA.

CS resta basso e DC alto per la finestra corrente, anche nelle pause tra blocchi.
La callback HAL libera il buffer dopo la fine della trasmissione SPI e avvia
il blocco successivo se è già pronto. Altrimenti la prossima chiamata a Process
riprende il trasferimento. Non si preparano pixel e non si attende il DMA
nelle callback della libreria. La HAL STM32G4 effettua comunque il proprio
controllo finale dei flag SPI prima di chiamare la callback applicativa.
Alla fine della finestra, Process seleziona la successiva o pubblica IDLE.

`ST7789_BLOCKING_MAX_PIXELS` (8 di default) evita di avviare DMA per finestre
minuscole: se l'intera finestra sta nel buffer ed è entro questa soglia,
Process esegue una breve trasmissione blocking, con interrupt abilitati.
Non si eseguono trasferimenti blocking negli interrupt. Impostare la soglia
a zero per usare DMA anche su ogni segmento di un pixel.

Il main inoltra `HAL_SPI_TxCpltCallback` e `HAL_SPI_ErrorCallback` al trasporto;
questo gestisce solo l'handle configurato. Se in futuro si aggiungono altri
utilizzatori delle callback HAL, conservarne l'instradamento nello stesso main.
Serve l'interrupt DMA TX già configurato in CubeMX. L'interrupt globale SPI
non è necessario per il normale completamento DMA; abilitarlo e instradarlo
da CubeMX se si vuole anche la gestione immediata degli errori IRQ della SPI.

## Stato ed errori

- IDLE: nessun disegno asincrono in corso.
- BUSY: l'intera operazione è attiva, anche quando il DMA aspetta un buffer.
- ERROR: errore di configurazione, chiamata HAL o trasferimento; nessun retry.

GetError restituisce l'ultimo risultato HAL locale. Il completamento non
conferma che il display abbia ricevuto correttamente i dati. Dopo un errore
runtime ClearError può ripristinare IDLE solo se HAL è READY; il disegno
parziale non viene ripreso. Se HAL non è READY, correggere/ripristinare prima
la periferica. Se Init fallisce, correggere il problema e richiamare Init.

Rotazione (1 o 3), inversione e tearing rimangono comandi blocking brevi;
restituiscono BUSY se un disegno DMA è in corso.

## Integrazione UI

Il main inizializza ST7789 e UI, poi chiama `ST7789_Process()` e `UI_Process()`
a ogni giro del superloop. La UI è l'unico utilizzatore delle API di disegno;
la Home mostra una prima dashboard. La scheda segnala un errore runtime
impostando il GPIO Board_LED alto.


## Font e pannelli arrotondati

`st7789.h` include `Fonts/fonts_generated.h`. WriteString e WriteChar ricevono
un `FontId`, per esempio `FONT_INTER_MEDIUM_10`; il renderer legge dimensioni,
metriche e bitmap dal descrittore `Fonts[id]`. CMake compila solo il registro
nuovo, non il vecchio fonts.c. Per rigenerare i font, usare lo script
`Firmware/Scripts/FontGeneration/generate_font.py` con il relativo fonts.json.

DrawRoundedRectangle riceve x, y, larghezza, altezza, raggio e tre colori:
bordo, interno e sfondo esterno agli angoli. Il bordo è spesso un pixel.
Impostare bordo e interno allo stesso colore per un pannello pieno.
Il riquadro completo viene generato in una finestra continua, tramite i buffer
DMA esistenti: nessun framebuffer. La UI lo usa per la struttura statica;
è più semplice del tracciare separatamente linee e archi, ma trasferisce anche
lo sfondo interno al riquadro. Raggio minimo 1 e diametro minore di entrambi i
lati; il riquadro deve stare interamente sul display.

Gli angoli esterni e il confine fra bordo e riempimento usano copertura
calcolata con 4x4 campioni per pixel. I contributi di bordo, riempimento e sfondo
sono combinati direttamente in RGB565. Il campionamento riguarda solo la fascia
vicina alla curva: interno, esterno e tratti rettilinei hanno percorsi rapidi.
Nessuna bitmap aggiuntiva o allocazione; preparazione nei blocchi del super loop,
senza modificare triangoli, linee o le altre primitive.

## Numeri dinamici

ST7789_WriteNumberField(x, y, width, number, font, color, background) è l'unica
modalità numerica. Accetta 0..9, +, - e punto, oppure una stringa vuota per
cancellare il campo. Non formatta o interpreta il valore; non accetta suffissi.

Cifre e segni usano uno slot comune abbastanza largo da contenerli tutti.
I glifi sono centrati nel proprio slot, mantenendo gli offset verticali;
il punto conserva uno slot più stretto. La larghezza si calcola con questi
stessi avanzamenti e il numero è sempre allineato al bordo destro dell'area.
La sostituzione di una cifra non muove le altre. A parità di precisione,
il punto decimale resta fisso. L'App mantiene quindi lo stesso formato, per
esempio sempre un decimale. Non ci sono opzioni di allineamento per i numeri.

Il campo completo viene riscritto in una finestra DMA, riutilizzando il renderer
esistente. La stringa deve restare invariata fino a IDLE. Caratteri non ammessi
o un numero che non entra restituiscono INVALID_ARGUMENT. MeasureText resta
la misura del testo proporzionale; la modalità numerica calcola internamente
il proprio ingombro. I descrittori generati non richiedono modifiche.

## Asset indicizzati

`Assets/assets_generated.h/.c` è il registro generato dai PNG RGBA configurati
in `Scripts/SymbolsGeneration/assets.json`. CMake compila il registro una volta;
il Python riscrive solo i due file generati. L'ID INVALID non è disegnabile.

DrawAsset(x, y, id, angle_deci_deg, background) legge bitmap e palette
RGB565 dalla Flash. Ogni pixel occupa un byte: indice colore a 4 bit nel nibble
alto e alpha a 4 bit nel nibble basso (0 trasparente, 15 opaco). Tutti i 16
colori sono disponibili. Una sola finestra quadrata fissa, di lato
max(width,height), senza framebuffer o scaling a runtime. I pixel sono preparati
nei buffer DMA esistenti. L'angolo positivo ruota in senso orario; zero mantiene
l'orientamento originale. Campionamento inverso con interpolazione bilineare dei quattro pixel vicini:
le componenti R/G/B sono interpolate separatamente con pesi interi a 8 bit e
arrotondamento finale. Ogni campione viene composto sul background usando
il suo alpha prima dell'interpolazione; fuori immagine si usa background.
Le semitrasparenze funzionano anche sulle icone ferme. Calcoli interi per pixel
e seno/coseno una volta per richiesta. I vecchi asset a 4 bpp vanno rigenerati.
Il filtro richiede più CPU rispetto alla scelta di un solo pixel, ma non cambia
la RAM dei buffer o il numero di pixel SPI trasferiti.

Il PNG ruota nel riquadro originale: usare artwork circolare con angoli
trasparenti per il volante, altrimenti le parti che escono vengono tagliate.
La trasparenza sostituisce i pixel con uno sfondo uniforme passato dal chiamante,
non conserva il contenuto del display. La compressione riduce la Flash, mentre
SPI continua a inviare RGB565. Il generatore permette `--size N` e size per voce
JSON; il resize avviene prima della quantizzazione. Vedere il suo README.

## Antialiasing dei font

Tutte le API di testo, inclusi i numeri tabulari, usano copertura 0..15 generata
da Pillow. Il colore dei pixel intermedi viene preso da una palette RGB565
precalcolata usando foreground e background della richiesta. Non si legge il
display: lo sfondo deve essere quello uniforme del campo. Il renderer usa gli
stessi buffer DMA e gli stessi byte SPI del testo precedente, più 32 byte per
la palette. Il formato degli asset grafici e il loro filtro non sono modificati.

## Barra di avanzamento arrotondata

`ST7789_DrawProgressBar(x, y, w, h, filled, color, track, background)` disegna
in una sola finestra il fondo e il riempimento raccordati, con antialiasing
4x4 sui bordi. `filled` è una larghezza in pixel saturata a w; zero svuota la
barra, w la riempie. Servono w >= h >= 2 e riquadro interamente sul display.
Si usa uno sfondo uniforme, senza lettura del display o framebuffer aggiuntivo.

## Grafico a una o due serie

`ST7789_DrawGraph(&descriptor, samples, count)` disegna un rettangolo contenente
sfondo, griglia tratteggiata e due curve in un solo job. ST7789_Graph definisce
posizione, dimensioni, minimo/massimo Y comuni, colori e series_count (1 o 2).
Con una serie si usa soltanto il campo a. ST7789_GraphSample
contiene due int16_t; le unità sono decise dal chiamante. Si usa un campione
per colonna, da vecchio a recente. count deve essere <= width e i campioni sono
allineati a destra durante il riempimento iniziale; count zero mostra la griglia.
Valori fuori scala vengono clampati ai bordi. I segmenti sono rasterizzati a un
pixel, senza filtri aggiuntivi in questa prima versione. Nei pixel coincidenti
i colori A/B si alternano ogni 4 colonne per mantenere riconoscibili entrambe le serie. Il driver non conserva lo storico e non gestisce validità.

Descrittore e array devono restare validi e immutabili fino a IDLE. La UI usa
una copia stabile dei soli campioni; il driver continua a generare al massimo
un blocco di ST7789_BUFFER_PIXELS per Process, senza framebuffer aggiuntivi.
