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
- I cerchi pieni usano segmenti orizzontali. Le circonferenze scrivono un anello
  radiale di un pixel e preservano il disco interno. Il calcolo usa una radice
  quadrata intera: la rasterizzazione può differire dall'originale midpoint.
- Il testo usa una finestra per carattere e genera pixel di testo e sfondo.
  Supporta ASCII 32..126, newline e ritorno a capo al bordo destro; gli altri
  byte sono sostituiti con '?'. La scrittura si ferma al bordo inferiore.

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

## Demo

La demo nel main è una macchina a stati che aspetta IDLE dopo ciascun disegno,
comprese le scritte. Mostra colori, tempi di riempimento e dimensione dei buffer;
Poi mostra per due secondi una sfumatura magenta -> nero -> magenta;
infine disegna barre, contorni e forme piene, e fa lampeggiare un quadrato.
Le stringhe dei risultati sono persistenti, non array locali temporanei.
Le immagini demo grandi non sono usate e non sono state abilitate.

`display_last_fill_ms` misura l'ultimo riempimento completo, compresa la
preparazione, l'impostazione della finestra e il ritardo con cui il main osserva
IDLE. Il tempo è mostrato sul display dopo la misura, senza includere le scritte.
La scheda segnala un errore runtime impostando il GPIO Board_LED alto.

