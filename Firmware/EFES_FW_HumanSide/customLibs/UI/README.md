# UI

Modulo cooperativo sopra ST7789. Stato, navigazione e temporizzazione sono
privati. Home, Sensor Diagnostics e Steering Response sono le tre pagine
navigabili 320x240;
la pagina Allarme è ancora vuota. Lo sfondo viene cancellato soltanto all'avvio o al cambio pagina.

## Integrazione

Il main inizializza GPIO, DMA, SPI e ST7789, poi chiama `UI_Init()` una volta.
Nel superloop chiama sempre entrambe:

```c
ST7789_Process();
UI_Process();
```

Tutte le API UI si chiamano dal main, mai dagli interrupt. La UI è l'unico
modulo che richiede disegni a ST7789; le callback SPI restano instradate dal main.

- `UI_SetState(&state)` copia i dati senza disegnare. Lo stato contiene angolo
  richiesto, velocità, angoli A/B, limite configurato FPGA, validità dei canali,
  flag di plausibilità e stato CAN/attuatore.
  Gli angoli sono espressi in decimi di grado: `245` significa `+24.5 deg`.
  Velocità: 0..999 km/h. Il limite diagnostico deve essere maggiore di zero.
  La differenza assoluta viene calcolata nella UI, non fornita dall'App.
  La maschera `alarms` forza la pagina Allarme quando diversa da zero;
  i singoli bit saranno definiti con l'App.
- `UI_PostEvent(UI_EVENT_NEXT_PAGE)` e `UI_EVENT_PREVIOUS_PAGE` inseriscono
  azioni in una FIFO di 8 elementi. Al massimo un evento viene consumato per
  chiamata a Process. L'inserimento restituisce false se la coda è piena,
  l'evento non è valido o è attivo un allarme.
- `UI_SetRefreshPeriod(ms)` cambia il periodo e riavvia il timer; il default
  è 20 ms. Gli aggiornamenti si fondono in una sola richiesta pendente.

Next/Previous passano ciclicamente fra Home, Sensor Diagnostics e Steering Response.
Con `alarms != 0` la UI passa alla pagina Allarme appena la primitiva ST7789
attiva termina, senza attendere il timer. Gli eventi di navigazione pendenti
vengono scartati. La pagina scelta dall'utente viene conservata e ripristinata
quando gli allarmi cessano.

## Rendering

`UI_home.c` contiene il layout e la sequenza di disegno della Home. Riceve
lo snapshot `ui.render_state`, effettua un piccolo passo per chiamata e
restituisce true al completamento. Lo snapshot resta stabile durante il refresh;
le nuove chiamate a SetState aggiornano soltanto i dati del prossimo refresh.
I buffer di testo sono persistenti fino a fine disegno.

La struttura statica viene disegnata una volta. Nei refresh successivi si
aggiornano solo i campi cambiati. La barra lineare ha fondo scala +/-450 gradi
con quattro segmenti separati per lato. Il riempimento è progressivo dentro
ogni segmento e riscrive solo i tratti che cambiano, lasciando intatto lo zero.
Il valore numerico conserva l'angolo ricevuto anche oltre il fondo scala.

Il volante usa `ST7789_DrawAsset` con `UI_WHEEL_ASSET` (ASSET_STEERING_WHEEL):
una finestra 83x83, con palette RGB565 e alpha a 4 bit miscelato con lo sfondo, senza framebuffer
aggiuntivo o cancellazione separata. La posizione grafica è quantizzata a un
grado; il numero mantiene i decimi. I font sono generati da fonts.json:

| Uso | Font enum | Altezza riga |
| --- | --- | --- |
| Angolo | FONT_RAJDHANI_BOLD_38 | 29 px |
| Velocità, delta, rapporto | FONT_RAJDHANI_SEMIBOLD_28 | 21 px |
| Titoli | FONT_INTER_MEDIUM_12 | 15 px |
| Unità, scala, direzione | FONT_INTER_MEDIUM_10 | 13 px |
| Stati | FONT_INTER_SEMIBOLD_11 | 14 px |
| Modalità | FONT_RAJDHANI_BOLD_28 | 26 px |

I font restano proporzionali, senza kerning. Titoli e testi sono centrati in
campi larghi un numero di pixel, tramite ST7789_WriteTextField. Angolo,
velocità, delta e rapporto usano ST7789_WriteNumberField: cifre e segni hanno
slot uniformi, il punto uno slot più stretto, e il bordo destro è fisso.
Con precisione decimale costante, cambiando una cifra le altre non si spostano.
La comparsa di una nuova cifra estende il numero a sinistra. Il suffisso :1 del
rapporto e i gradi sono elementi statici, esterni ai campi numerici. Il campo
viene aggiornato in una sola finestra opaca, senza cancellazione separata o
padding con spazi. Il testo vecchio non rimane quando il valore si accorcia.
Anche i numeri riscrivono il campo intero, senza una seconda macchina a stati
per aggiornare singole cifre. Il segnaposto sensori --.- usa la stessa modalità.
ST7789_MeasureText e il renderer usano le stesse metriche individuali.

I font numerici esportano solo l'intervallo necessario, per ridurre la Flash. Il grado usa il byte 0xB0 di Inter Medium. Il footer dipende dalla modalità di guida. Pannelli e footer usano una primitiva ST7789 arrotondata,
con raggio rispettivamente di 4 e 5 pixel. I pannelli sono opachi e vengono
generati a blocchi, una sola volta all'ingresso nella pagina.
La pagina Allarme resta da implementare.

Il main simula un percorso ciclico di 40 secondi: partenza, accelerazione fino
a 55 km/h, curve leggere, rallentamento e manovre a +/-450 gradi. I valori sono
interpolati fra i punti di `demo_route`, modificabili nel main.
Negli ultimi tre secondi, a veicolo fermo, si alternano sensori non validi,
CAN offline e attuatore non pronto; il ciclo successivo ripristina gli stati.
Gli allarmi restano a zero perché la pagina Allarme è ancora vuota.

La simulazione usa HAL_GetTick, indipendentemente da TIM6: angolo ogni 10 ms,
velocità ogni 100 ms, differenza sensori e stati ogni 250 ms. Non usa attese
né riproduce campioni arretrati se il main è in ritardo. In seguito sarà l'App
a sostituire Demo_Process e chiamare SetState con i dati reali.

Il timer regola l'inizio dei refresh. Il rendering attivo avanza a ogni giro,
anche senza nuove scadenze. Non ci sono attese, code di frame o retry automatici
degli errori ST7789. Il main segnala l'errore del driver con Board_LED.

## Timer

`UI_timer.c` riserva TIM6 e il vettore `TIM6_DAC_IRQHandler` alla UI.
Configurazione e registri sono confinati in questo file; non serve abilitare
TIM6 in CubeMX né aggiungere il driver HAL TIM. Non assegnare lo stesso timer
o vettore ad altri utilizzatori.

Il contatore lavora a 10 kHz usando il clock APB1 del progetto. Il periodo è
compreso fra 1 e 6553 ms. L'ISR azzera la richiesta hardware e imposta un flag;
il main lo consuma con una breve sezione critica. Enable, Disable e Reset
rimangono nell'API privata del timer.

## Layout e simboli

La Home ha una riga superiore senza riquadri (SENSOR, CAN, MOTOR), un pannello centrale
con volante e richiesta di sterzo, tre riquadri inferiori (velocità, differenza
sensori, rapporto di sterzo) e il footer NORMAL. Le etichette sono abbreviate
per il display 320x240 e i nuovi font proporzionali. Il rapporto arriva da
`steering_ratio_deci`: 128 significa 12.8:1. La demo lo varia con la velocità;
questa è soltanto una mappa dimostrativa nel main, non un calcolo della UI.

Le etichette superiori sono fisse, con pallini di raggio 4 pixel:
sensore a (102,18), CAN a (194,18), motore a (308,18). Verde indica valido /
online / pronto; sensore non valido e CAN offline sono rossi, motore non pronto
arancione. La direzione compare solo accanto all'angolo. La barra mantiene
quattro segmenti per lato e il riferimento centrale, senza contorno esterno.

Gli spazi per le icone sono lasciati vuoti. Dimensioni native, senza scaling:

| Simbolo | Dimensioni | Posizione x,y |
| --- | --- | --- |
| Sensore (stato superiore) | 16x16 | 7,9 |
| CAN | 16x16 | 113,9 |
| Road ECU | 16x16 | 219,9 |
| Velocità | 16x16 | 8,145 |
| Differenza sensori | 16x16 | 114,145 |
| Mappa sterzo | 16x16 | 220,145 |
| Veicolo nel footer | 24x24 | 91,209 |

Sfondo pagina: RGB565 `0x0022`; interno card: `0x0884`; bordi: `0x21AC`;
footer: `0x3934`. Testi e trasparenza del volante usano lo sfondo della card.
Con DrawImage le immagini sono RGB565, byte alto per primo, senza alpha.

Le card inferiori mostrano solo titolo e valore con unità/suffisso. I titoli
SPEED, DELTA e MAP sono allineati a sinistra a y=147; i valori iniziano a y=170,
con spazio libero fra titolo e valore. SIM/REAL, VALID/INVALID e
Adaptive non sono visualizzati; la validità dei sensori resta nel pallino
superiore e nel segnaposto numerico --.-.

La funzione geometrica ST7789_DrawSteeringWheel resta disponibile nella libreria,
ma la Home usa esclusivamente l’asset. La rotazione è eseguita a runtime.

## Modalità di guida e layout

`UI_State.drive_mode` seleziona `UI_DRIVE_NORMAL`, `UI_DRIVE_ECO` o
`UI_DRIVE_SPORT`. La Home associa testo e colore: viola, verde e rosso.
Il footer viene ridisegnato solo al cambio modalità, con macchinina a sinistra
ed etichetta a destra, separate da una barra verticale con 8 pixel liberi
per lato. Il gruppo è centrato usando MeasureText.
La demo cambia modalità ogni 10 secondi, dal suo clock dati indipendente dalla UI.

Le icone statiche sono 20x20, con 4 pixel fra box e testo e centri verticali
allineati. SENSOR usa `ASSET_SENSOR`, generato da `source/Sesnsor_Symbol.png`.
`UI_FONT_DIRECTION` controlla RIGHT/LEFT/ZERO (Inter Medium 10 inizialmente).
L'angolo è a y=68, quattro pixel più in basso; lo slider è alto 8 pixel.
Le misure temporanee W/P, la relativa API e la strumentazione DWT sono rimosse.

Tutti i testi della Home sono antialias con 16 livelli di copertura: etichette,
stati, modalità e numeri dinamici. Il generatore conserva le sfumature
del font, il renderer le combina con lo sfondo corretto della pagina, della card
o del footer. Posizioni, metriche e allineamento tabulare non cambiano.
Gli asset grafici non sono modificati da questo aggiornamento.

## Riga di stato Home

La testata mostra SENSORS, CAN e ROAD ECU in chiaro, ciascuno preceduto da
un simbolo 16x16: tick verde se valido/online/pronto, cross rossa altrimenti.
Le vecchie icone e i pallini della testata non vengono più disegnati.
Il simbolo si aggiorna soltanto quando cambia lo stato corrispondente.
`STATUS_OK_COLOR` e `STATUS_ERROR_COLOR` in UI_home.c definiscono i colori.
`ST7789_DrawSymbol` usa l'alpha dell'asset e il colore RGB565 passato dal C,
ignorando la palette originale; DrawAsset mantiene invece i colori originali.
Il JSON include TICK e CROSS e il generatore produce solo il registro generato.

## Sensor Diagnostics

`UI_sensor.c` disegna due card A/B, una card di deviazione e una card
CHANNEL HISTORY A/B con grafico rolling a due curve.
Le cifre usano la modalità numerica tabulare con bordo destro fisso.
I font sono selezionabili tramite i define SENSOR_FONT_* all'inizio del file.

Dati richiesti in UI_State (angoli e limite in decimi di grado):

- `channel_a_angle_deci_deg`, `channel_b_angle_deci_deg`: misure provenienti dall'FPGA.
- `channel_a_valid`, `channel_b_valid`: validità dei singoli canali dal sensore.
- `sensor_deviation_limit_deci_deg`: fondo scala configurato nell'FPGA, maggiore di zero.
- `sensor_plausibility_fault`: verdetto del sensore ricevuto via SPI o GPIO.

UI_SensorDeviation calcola soltanto abs(A-B), condiviso anche dal DELTA Home.
La barra rappresenta min(deviazione / limite, 1). Con flag fault attivo diventa
completamente piena e rossa; il numero resta reale. Non ci sono etichette
NORMAL/OVER LIMIT. Senza flag resta verde, anche se la deviazione supera il fondo
scala. Non ci sono warning né confronti software per decidere la plausibilità.
Il limite non viene scritto sul display. `alarms` resta indipendente: questo
flag diagnostico non attiva automaticamente la pagina Allarme.

`UI_header.c` è l'intestazione comune delle pagine secondarie: titolo e pallini
con pagina attiva azzurra, allineati a destra. Si disegna all'ingresso, prima dei dati.
Non viene mostrato il numero di pagina. Il numero di pallini deriva da PAGE_COUNT:
aggiungere una pagina alla navigazione aggiorna anche gli indicatori.

App_Process in Core/Src/App.c legge USER_Button (PC13) già configurato da
CubeMX come ingresso. Una pressione stabile per 30 ms invia UI_EVENT_NEXT_PAGE;
tenere premuto non ripete l’evento. APP_BUTTON_PRESSED definisce il livello
attivo: GPIO_PIN_SET, coerente con PC13 configurato pull-down e con il
cambio al rilascio osservato usando GPIO_PIN_RESET. Non si usano interrupt o attese bloccanti.
Il main chiama App_Init dopo GPIO/UI e App_Process nel superloop.
Il cambio pagina automatico della demo è rimosso; i dati continuano ad
aggiornarsi con i propri periodi indipendenti dal refresh UI. Il limite provvisorio vale
10 decimi (1 grado), impostato solo nella configurazione dei dati simulati.
Nel ciclo dati di 40 secondi:

- Fra 26 e 28 s la deviazione aumenta fino a superare il fondo scala, senza flag.
- Fra 28 e 32 s arriva il flag simulato: barra piena rossa e deviazione reale 1.4 gradi.
- A 32 s il flag si spegne e la barra torna verde; a 37 s viene simulato anche
  un canale B non valido per un secondo.

Le sorgenti simulate producono il flag secondo la sequenza temporale: non
esiste nel renderer un controllo che ricavi il fault dal valore degli angoli.

La testata secondaria è una fascia 320x22 senza contorni laterali o superiori,
con sfondo HEADER_BACKGROUND e una sola linea in basso. La deviazione occupa
42 pixel in altezza: titolo e barra da 156 pixel a sinistra, numero grande a
destra. La card storica inizia a y=134 ed è alta 102 pixel.

Le card A/B sono alte 56 pixel e mostrano soltanto titolo e angolo con font
Rajdhani Bold 40. VALID/INVALID e i pallini sono rimossi dal renderer diagnostico;
i flag di validità restano nello stato per gli altri usi. La deviazione conserva
Rajdhani Bold 42, così resta il valore principale della pagina.

## Freschezza dei campioni e stato dello storico

`UI_State.sensor_sample_received_at_ms` contiene HAL_GetTick all'arrivo della
coppia A/B dal sensore. L'App aggiorna questo campo soltanto ricevendo un nuovo
campione, non a ogni UI_SetState e non quando cambiano CAN, velocità o modalità.
La UI usa la sottrazione unsigned dei tick; oltre 1000 ms i campioni sono stale.
L'età viene catturata una volta per refresh per mantenere colori coerenti.

Nella riga CHANNEL HISTORY, LAST UPDATE mostra:

- LIVE - <1s ago in verde quando entrambi i canali sono validi e recenti.
- STALE - >1s ago in giallo quando i canali sono validi ma non aggiornati.
- FAULT in rosso, senza tempi, quando un canale è invalido o il flag di plausibilità è attivo.

Un canale invalido forza barra piena rossa e N/A rosso, senza simbolo dei gradi.
Un fault di plausibilità hardware forza barra piena rossa e conserva la deviazione
numerica reale. Questi due casi hanno priorità su stale. Altrimenti stale rende
gialli barra e numero, senza cambiare il riempimento. Il verdetto di plausibilità
resta esclusivamente hardware: la UI valuta soltanto la freschezza dei dati.
Lo stato dello storico mostra FAULT anche quando è attivo il flag di plausibilità
hardware, indipendentemente dalla freschezza.

La barra usa ST7789_DrawProgressBar: fondo e riempimento raccordati e antialias,
preparati in un unico job nei buffer DMA, senza framebuffer aggiuntivo.
La demo interrompe i campioni da 20 a 23 s del ciclo per mostrare STALE e recupero;
a 37 s rende invalido il canale B per un secondo per mostrare FAIL/N/A.
Il grafico usa lo storico descritto sotto.

## Grafico rolling della deviazione

Configurazione in UI_history.h:

```c
#define GRAPH_WIDTH_PX 264U
#define GRAPH_HISTORY_MS 10000U
#define GRAPH_REFRESH_MS 100U
#define GRAPH_DEVIATION_SCALE 2U
```

DEVIATION HISTORY mostra una sola curva turchese: abs(A-B), in decimi di grado.
La scala verticale va da zero a due volte il limite configurato FPGA (0..2 gradi
nella demo). Non segue automaticamente minimo e massimo dei dati. Se il limite
configurato cambia, assi e grafico vengono aggiornati. Il valore reale resta nel
campo numerico; solo la rappresentazione nel grafico viene ritagliata al fondo
scala. La scala non decide mai lo stato di plausibilità e non viene disegnata
una linea di allarme.

UI_history.c conserva 264 coppie int16_t in un ring da 1056 byte. Conservare A/B
permette di calcolare la deviazione nella copia grafica senza modificare i dati
storici. Un indice circolare evita spostamenti a ogni inserimento. UI_Process
campiona anche sulla Home e durante il DMA. Il periodo medio è 10000/263 ms,
circa 38.023 ms: l'accumulatore conserva la frazione senza timer in microsecondi.
Un ritardo non genera inserimenti retroattivi di campioni inventati.

Con un canale invalido, flag di plausibilità o STALE, il ring continua ad avanzare
ripetendo l'ultima coppia utilizzabile. La curva resta quindi piatta in quel
tratto: è un valore mantenuto, non una nuova misura. Lo stato FAULT/STALE lo
segnala separatamente. Al recupero si accodano i nuovi dati, senza cancellare lo
storico. Prima del primo campione utilizzabile il grafico mostra solo la griglia.
Soltanto UI_Init azzera gli indici; cambiare pagina non azzera mai lo storico.

UI_sensor.c copia il ring in un array statico da 1056 byte, converte ciascuna
coppia nella deviazione e ridisegna soltanto il rettangolo 264x46 ogni 100 ms.
La copia resta stabile fino a IDLE, mentre il ring continua a campionare.
Ring e copia occupano 2112 byte, oltre a pochi dati di controllo. Durata dello
storico e periodo di disegno non cambiano questi consumi; la larghezza sì.

ST7789_DrawGraph genera sfondo, griglia e curva in una finestra DMA usando i
buffer esistenti. Nessun framebuffer completo o spostamento dei pixel del display.
Assi, titolo e legenda restano statici salvo variazioni della scala configurata.
Font, colori e posizioni sono definiti in UI_sensor.c. STALE mantiene barra e
numero gialli con ultimo valore; i fault hardware restano prioritari.

## Steering Response

La terza pagina usa UI_Header_Process come Sensor Diagnostics. I tre pallini
sono derivati da PAGE_COUNT; USER_Button passa alla pagina successiva e torna
alla Home dopo Steering Response.

Dati forniti dall'App tramite UI_SetState:

- road_requested_angle_deci_deg: comando destinato alla centralina road-side.
- road_actual_angle_deci_deg: angolo effettivo riportato dal road-side.
- road_feedback_received_at_ms: HAL_GetTick all'arrivo del feedback, senza
  aggiornarlo quando cambiano soltanto altri dati.
- road_feedback_valid: validità del feedback; can_online indica la connessione.

Requested e actual devono rappresentare lo stesso angolo lato strada, con
stesso zero, segno e unità (decimi di grado). Il valore steering_angle_deci_deg
Home resta l'angolo al volante; la UI non lo converte tramite il rapporto di
sterzo. Il tracking error non viene calcolato o mostrato in questa pagina.

Le card numeriche usano requested giallo acceso e actual magenta acceso, con tabular numbers.
Lo storico mostra le due curve negli stessi colori e scala comune. Configurazione
in UI_steering.h:

```c
#define STEERING_GRAPH_WIDTH_PX 264U
#define STEERING_GRAPH_HISTORY_MS 10000U
#define STEERING_GRAPH_REFRESH_MS 100U
#define STEERING_GRAPH_MIN_ANGLE (-450)
#define STEERING_GRAPH_MAX_ANGLE 450
#define STEERING_FEEDBACK_STALE_MS 1000U
```

I limiti Y sono in decimi: inizialmente -45..+45 gradi alle ruote. Posizione,
altezza (58 pixel), colori e font sono nei define di UI_steering.c.

UI_trace.c contiene il ring e la temporizzazione frazionaria condivisi dai due
storici, con array statici separati. La terza pagina aggiunge 1056 byte per il
ring e 1056 per la copia stabile durante DMA. Il campionamento continua su tutte
le pagine; fault o stale ripetono l'ultima coppia utilizzabile, senza reset. Il
rendering riusa ST7789_DrawGraph con series_count=2 e ridisegna solo il grafico
ogni 100 ms. Etichette, assi, griglia e legenda usano il layout della pagina.

Stato feedback: LIVE se recente e valido, STALE oltre un secondo, FAULT se CAN
offline o feedback invalido. STALE mostra ultimo actual in giallo; FAULT
mostra N/A rosso. La UI non deduce allarmi dalla differenza requested/actual.

La demo produce comandi road-side a gradino ogni 5 secondi, indipendenti dalla
traiettoria volante usata dalla Home, per rendere visibile la risposta nel grafico.
Il motore simulato insegue il comando con una dinamica diversa per modalità:
COMFORT circa 250 ms, ECO 450 ms, SPORT 100 ms. Fra 18 e 20 s si interrompe il feedback; fra 38 e 39 s il CAN è offline e fra 39 e 40 s
il feedback è invalido. Il motore simulato continua a muoversi anche senza ricezione.

La modalità di guida compare nel footer di Steering Response, al posto del
tracking error. Il grafico è riposizionato a y=111 dentro la card a y=83;
assi e legenda lasciano spazio alla barra in basso a y=205.
UI_mode.c disegna il footer condiviso da Home e Steering Response: stesso
simbolo, separatore verticale, font e colori COMFORT/ECO/SPORT. UI_FONT_MODE è
in UI_mode.h; nomi e colori sono nella tabella modes di UI_mode.c. Il footer
si aggiorna soltanto all'ingresso nella pagina o quando cambia modalità.
La demo modifica la dinamica del motore, senza cambiare periodi di acquisizione
o rendering; le costanti sono in demo_motor_response_steps nel main.

In Steering Response colori di titoli, numeri, curve e legenda coincidono:
requested 0xFFE0 (giallo), actual 0xF81F (magenta). Nei pixel dove le due
curve si sovrappongono il renderer alterna tratti di 4 pixel nei due colori,
senza spostare i valori o nascondere completamente una serie.
