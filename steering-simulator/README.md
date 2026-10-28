# Steering Lab

Simulatore parametrico locale di un quadrilatero di sterzo, con staffe rigide e ruote reali nella vista dall'alto. **Python + NumPy, Streamlit e Plotly**, senza account, database o servizi cloud.

Implementa i primi quattro traguardi della specifica: nucleo matematico, simulazione interattiva, diagnostica e ricerca dimensionale. Include il comando con **leva motore e astina snodata al tirante**, configurabile manualmente. Non simula coppia o dinamica del motore.

## Avvio su Linux

Consigliato Python 3.12. Dalla cartella `steering-simulator`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run.sh
```

Apri **http://localhost:8501**. Per cambiare porta: `./run.sh --server.port 8502`.
Nel workspace di consegna l'ambiente `.venv` è già preparato; basta `./run.sh`.
L'installazione iniziale richiede accesso a PyPI. Dopo l'installazione l'app funziona localmente, senza connessione esterna.
Il server è vincolato a `127.0.0.1`; la raccolta delle statistiche Streamlit è disattivata.

Verifiche automatiche essenziali, con output breve:

```bash
.venv/bin/python -m pytest -q
```

Le versioni verificate nell'ambiente di sviluppo sono NumPy 1.26.4, Streamlit 1.66.0, Plotly 6.9.0, PyArrow 19.0.1 e Pytest 9.1.1. PyArrow è limitato a una serie compatibile con NumPy 1.x. SciPy non è necessario per questo traguardo: chiusura e punti morti si risolvono geometricamente, mentre la ricerca è una griglia limitata.

## Primo utilizzo

1. Nella scheda **Simulazione**, muovi **Angolo di sterzata** oppure premi **Avvia**. Il comando è la media `(θ SX + θ DX)/2`: +20° e −20° producono pose speculari, con angoli delle due ruote scambiati e di segno opposto. Le due ruote sono sempre calcolate dal vincolo rigido.
2. Le dimensioni iniziali sono un parallelogramma con interasse 180 mm, bracci 25 mm, entrambi rivolti al retro, e tirante 180 mm. A ±25° le due staffe ruotano dello stesso angolo; T percorre un arco.
3. Apri gli espansori nella barra laterale per cambiare staffe, posizione delle ruote, geometria. Gli offset ruota sono vettori indipendenti dalla direzione dei bracci.
4. Le staffe sono sempre simmetriche. I tre controlli della geometria sono **Lunghezza Braccio**, **Lunghezza Tirante** e **Inclinazione Bracci**: 0° indica bracci rivolti al retro, angoli positivi verso l’esterno e negativi verso l’interno. Gli offset della ruota DX sono specchiati automaticamente.
5. Le ruote sono sempre dritte nella posa iniziale. L’interasse dei perni viene calcolato automaticamente: `d = t − 2 L sin β`. Il valore è mostrato in sola lettura ed esportato per il CAD. Le combinazioni che producono un interasse non positivo vengono rifiutate. L’orientamento dei bracci non modifica l’orientamento iniziale delle ruote.
6. Metti in pausa o rilascia lo slider per acquisire la posa. In **Risposta cinematica**, premi **Calcola grafici e diagnostica**: una barra di avanzamento accompagna il calcolo dei sei grafici e della diagnostica cinematica. L'indicatore rappresenta la posa acquisita; i risultati restano fermi finché non richiedi una nuova analisi.
7. **Esplora progetti** confronta la corsa massima di liste di lunghezze braccio, inclinazioni e lunghezze tirante. I candidati conservano dimensioni e offset delle ruote; l’interasse dei perni viene calcolato per ogni candidato. Nessuno viene applicato senza il relativo comando.
8. **File e Onshape** permette salvataggio/caricamento JSON, export CSV (pulsante **Prepara risposta CSV**) e un elenco di variabili CAD da trasferire manualmente. Dopo un'analisi, la vista della posa acquisita nella scheda Risposta cinematica conserva l'esportazione SVG di Plotly.

### Animazione fluida e analisi separate

Il movimento è disegnato su un canvas locale tramite `requestAnimationFrame`, sincronizzato con il refresh del browser (tipicamente 60 Hz, dipendente dal dispositivo). Il browser ricava gli angoli delle ruote dall’angolo medio richiesto e risolve la chiusura esatta a ogni fotogramma: **nessuna interpolazione che allunghi le aste**. Python invia i parametri e le frontiere analitiche del ramo solo quando cambia il progetto. Non ci sono chiamate a Python, aggiornamenti Streamlit o ricostruzioni Plotly durante l'animazione.

Avvia/Pausa, slider, velocità, zoom, spostamento della vista e opzioni grafiche funzionano direttamente nel browser. Pausa, reset e rilascio dello slider inviano una singola posa a Python per l'eventuale analisi. I grafici, il confronto fra candidati e il CSV si calcolano soltanto con i rispettivi pulsanti, con indicatore di caricamento. Cambiando parametri vengono invalidati i risultati precedenti e la simulazione riparte ferma dalla posa zero. I controlli dei punti morti e del ramo restano attivi durante il movimento; gli ingombri fisici si verificano nella diagnostica su richiesta.

Il piccolo nucleo JavaScript dell'animazione replica la chiusura esatta e viene confrontato con il nucleo Python nei test di parità, incluse geometrie asimmetriche e i due rami. Non richiede librerie esterne né download dal browser. Gli inviluppi e le traiettorie vengono preparati una volta per geometria, non ricalcolati a ogni fotogramma.

### Dimensioni reali e dimensioni illustrative

Il modello conserva le lunghezze cinematiche, gli offset delle ruote e le dimensioni dei pneumatici (inizialmente 60 × 18 mm). La basetta, gli spessori, le quote Z e la ferramenta non sono modellati: si definiscono nel CAD.

La scheda **Ingombri 2D** raccoglie soltanto diametro ruote, larghezza pneumatici e larghezza comune dei braccetti (inizialmente 10 mm). La larghezza vale per bracci, staffe, tirante, leva e astina del motore; gli estremi rettangolari sporgono oltre il centro dei fori di metà larghezza. Queste misure aggiornano sia il browser sia la vista statica e il filtro delle interferenze, senza cambiare la cinematica. Viti, perni, spessori, quote Z e corpo motore non sono ostacoli. I simboli dei giunti sono decorativi e restano dentro i braccetti.

`docs/specification.md` conserva la specifica originale storica, antecedente alle semplificazioni concordate.

## Modello matematico

Lunghezze in **mm**, angoli interni e JSON in **radianti**, visualizzazione ed export CAD/CSV in **gradi**. X positivo verso destra, Y positivo verso il retro, fronte −Y. La visualizzazione pone +Y verso il basso e mantiene rapporto X:Y=1:1, con limiti indipendenti dall'angolo attuale.

```text
A SX = (−d/2, 0)                     A DX = (+d/2, 0)
b_i = L_i (cos α_i, sin α_i)          c_i = (offset_x_i, offset_y_i)
B_i = A_i + R(θ_i) b_i               C_i = A_i + R(θ_i) c_i
forward_i = R(θ_i + heading_offset_i) (0, −1)
F = |B DX − B SX|² − t² = 0
```

Per ogni θ SX, le intersezioni dei cerchi `(A DX, L DX)` e `(B SX, t)` determinano tutte le possibili pose. Il calcolo dell'altezza dell'intersezione usa una fattorizzazione di tipo Erone per ridurre la cancellazione vicino alla tangente. Nessuna ottimizzazione o deformazione delle aste è usata per ottenere la chiusura.

### Rami e movimento

Il ramo ± è il segno del prodotto vettoriale `(B SX − A DX) × (B DX − A DX)`. Il ramo −1 contiene la posa iniziale del parallelogramma. Il ramo non significa universalmente “aperto” o “incrociato”: dipende dalla geometria.

Il ramo che contiene le ruote dritte è selezionato automaticamente (−1 per le inclinazioni ammesse, fra −90° e +90° esclusi). Durante il moto, `BranchTracker` conserva il segno e svolge θ DX rispetto alla posa precedente. Prima di accettare una variazione, cerca tutte le frontiere geometriche nell'intervallo attraversato, usando:

```text
h² = d² + L SX² − 2 d L SX cos(θ SX + α SX)
h = L DX + t          oppure          h = |L DX − t|
```

La vista browser usa un intervallo simmetrico di sterzata media attorno alla posa zero, fino al primo punto morto di uno dei due lati. Le frontiere vengono ricavate dal modello geometrico; il limite è lo stesso verso destra e verso sinistra. Una richiesta oltre il limite viene ricondotta **all'angolo limite calcolato**, indipendentemente dalla velocità, dai fotogrammi o dalle richieste precedenti. La posa viene ricalcolata esattamente a quell'angolo: slider, lettura angolare, ruote e posa acquisita per l'analisi condividono il risultato. L'avviso riporta separatamente l'angolo richiesto quando supera il limite. Si può tornare verso il centro con lo slider o con Posa zero.

Le soglie prudenziali di trasmissione generano un allarme ma non arrestano una geometria ancora valida. L'animazione si ferma al limite geometrico; il rapporto cinematico resta sospeso vicino alla singolarità. Se il limite ha cerchi coincidenti, la posa non è univoca: si mostra l'angolo limite senza inventare una posizione della ruota destra o mantenere il disegno del fotogramma precedente. Il `BranchTracker` Python conserva il comportamento di rifiuto dei salti per gli utilizzatori del nucleo offline; l'animazione usa `motionLimits` e `resolveMotion` nel nucleo browser.

Cerchi coincidenti: angolo DX indeterminato e nessun risultato inventato. Cerchi concentrici diversi, geometria impossibile e aste nulle/negative: errore esplicito. Alla tangente c'è una singola posa con ramo 0; l'animazione si arresta. Il campionamento dei grafici aggiunge le frontiere analitiche e separa i tratti di curva.

### Diagnostica

```text
dvec = B DX − B SX
B'_i = J (B_i − A_i)
k = (dvec · B' SX) / (dvec · B' DX)
T = (1−λ) B SX + λ B DX
dT/dθ SX = (1−λ) B' SX + λ k B' DX
```

Le derivate di T sono **mm/rad**, non mm/°. Il rapporto cinematico è rad/rad (equivalente a °/°). La differenza fra ruote è la differenza degli heading, ricondotta a [−π,π], non la differenza degli orientamenti geometrici dei bracci α.

Tolleranza di lunghezza: `1e-10 × max(d, t, L SX, L DX)`. La trasmissione normalizzata è `|dvec · B'_i| / (t L_i)`. La soglia numerica è 1e-9; la soglia ingegneristica predefinita è **0.05**, costante interna. Presso il punto morto di uscita k e le derivate di T sono omessi, anche nei grafici e nel CSV. Il lato ingresso ha un allarme separato di trasmissione inefficace.

La distanza dal punto morto è la distanza angolare in θ SX dalla più vicina tangente o coincidenza dei cerchi, calcolata nell'intero periodo; è infinita quando tali frontiere non esistono. Non è una distanza spaziale tra pezzi. È mostrato anche il margine radiale `min(r+t−h, h−|r−t|)` in mm.

## Corsa massima: risultato della geometria

La prima scheda mostra immediatamente la sterzata media massima nei due versi, fino al primo punto morto o a 90°. Il calcolo non dipende dalla corsa impostata per lo slider, dalla velocità, dalle dimensioni dei pneumatici o dai fotogrammi. Sono riportati anche gli angoli delle due ruote al limite: verso opposto, i valori si scambiano e cambiano segno.

Il valore al punto morto identifica la fine della corsa del ramo collegato alla posa neutra, non un punto da attraversare. Se la geometria raggiunge 90° senza prima incontrare una singolarità, la scheda indica 90° raggiunti. La simulazione e il suo slider possono esplorare una corsa più corta, ma mai superiore a 90°.

Non ci sono obiettivi da impostare per rapporto fra ruote, differenza angolare o margini di allarme. Le differenze fra angoli delle ruote restano informazioni cinematiche, non errori da penalizzare. Gli allarmi diagnostici usano una costante interna 0.05; non definiscono la corsa geometrica. Non sono eseguiti controlli di interferenza, neppure fra le due ruote.

La ricerca confronta fino a 200 candidati variando lunghezza braccio, inclinazione e lunghezza tirante. Li ordina per sterzata media massima raggiungibile, senza criteri di conformità o vincoli di interferenza. La verifica del montaggio fisico resta al CAD e al prototipo.

## Configurazioni e CAD

`configs/default.json` contiene la configurazione iniziale. Il formato è versionato (`schema_version: 6`) e include unità, geometria cinematica, dimensioni delle ruote e larghezza comune dei braccetti, geometria motore, intervallo visualizzato, λ, simmetria e ramo selezionato. Gli angoli nel JSON sono in radianti. Lo schema 5 è ancora leggibile: in assenza della larghezza dei braccetti viene usato il precedente valore grafico di 10 mm, visibile e modificabile nella nuova scheda. I vecchi file degli schemi 1, 2, 3 e 4 sono rifiutati esplicitamente, senza conversioni automatiche o parametri nascosti. Il caricamento nell’app richiede staffe simmetriche, ruote dritte a zero, ramo neutro e interasse coerente con le tre regolazioni; configurazioni incompatibili vengono rifiutate senza modificarne silenziosamente le quote. Il caricamento controlla finitezza, intervalli e coerenza della simmetria; non esegue codice dal file. La posa temporanea e lo stato play/pausa non sono dimensioni del progetto e non vengono salvati.

L'export Onshape elenca nomi, valori, unità ed espressioni `#Nome_variabile`; contiene le sole dimensioni cinematiche e delle ruote; non esporta quote costruttive o dimensioni illustrative. Non esiste alcuna connessione automatica a Onshape. Procedura suggerita:

1. Crea le variabili nel Part Studio usando i nomi esportati.
2. Posiziona A SX/DX a ±`#Interasse_sterzo/2` e realizza i bracci con interassi `#L_braccio_SX/DX`.
3. Usa i vettori offset e gli orientamenti per posizionare correttamente ruote e staffe, senza imporre la collinearità A–B–C.
4. Usa `#L_SteeringRod` come distanza fra i due centri dei giunti rotanti.
5. Fissa i perni alle coordinate previste e progetta il supporto in CAD; imponi connessioni rigide staffa–braccio e rotanti ai quattro giunti. Controlla il ramo iniziale e non forzare un moto lineare del tirante.

## Architettura

```text
app.py                      interfaccia e analisi tecniche su richiesta
steering/parameters.py      dataclass immutabili, unità, JSON e validazione
steering/geometry.py        rotazioni, poligoni, intersezioni di cerchi
steering/kinematics.py      soluzione esatta, ramo, continuità, campionamento
steering/singularities.py   rapporto, velocità, margini e punti morti
steering/optimization.py    corsa geometrica massima e confronto dei candidati
steering/export.py          variabili CAD e CSV
steering/motor.py           leva + astina, settore continuo, sensibilità e CSV motore
visualization/              vista dall'alto e sei grafici diagnostici
visualization/browser/      animazione canvas locale e chiusura esatta JavaScript
visualization/browser_motion.py  collegamento del canvas a Streamlit
configs/default.json       parametri iniziali
tests/                     invarianti geometrici e controlli numerici mirati
```

Per usare il nucleo senza GUI:

```python
import math
from steering.parameters import Parameters
from steering.kinematics import BranchTracker
from steering.singularities import diagnose

p = Parameters()
motion = BranchTracker(p)
pose = motion.move(math.radians(25))
if pose is not None:
    print(math.degrees(pose.theta_right), diagnose(p, pose).ratio)
```

I test coprono i casi richiesti del modello passivo: parallelogramma neutro e in rotazione, conservazione della lunghezza, rigidità A/B/C, impossibilità, tangenti, centri coincidenti, continuità dei due rami, rifiuto dei salti oltre singolarità, scalatura, bracci da 40 mm, asimmetria, derivate contro differenze finite, offset heading, JSON e indipendenza della corsa da slider e ruote.

## Motore: collegamento manuale con leva e astina

Il collegamento è `M → Q → T`: M è il centro fisso dell’albero in uscita dal riduttore, M–Q la levetta, Q–T l’astina rigida snodata e T un punto materiale del tirante. I soli nuovi parametri sono posizione X/Y di M, lunghezza della leva, lunghezza dell’astina e montaggio A/B. L’attacco T si sceglie con λ (0 = SX, 0.5 = centro, 1 = DX). Questi parametri restano regolabili manualmente; la ricerca discreta si esegue soltanto nella pagina dedicata.

I valori iniziali (M = −60,25 mm; leva 15 mm; astina 60 mm; montaggio A) sono un esempio modificabile. Con lo sterzo iniziale consentono circa −36°/+38° di sterzata media, con sensibilità centrale circa 0.61 °sterzo/°albero. Non sono dimensioni validate per la fabbricazione.

La vista parte dal comando **Motore**: lo slider e la velocità si riferiscono all’albero, con 0° definito automaticamente nella posa con ruote dritte. **Sterzata libera** permette di osservare il solo sterzo; fuori dalla corsa continua dell’attuatore l’astina viene omessa con un avviso, senza deformarla per raggiungere una posa impossibile. Se il montaggio non chiude già al centro, il comando motore è disabilitato e viene spiegato il problema. Il montaggio A/B è mantenuto fisso durante il movimento.

La scheda **Motore e sensibilità** calcola su richiesta due curve: `m(φ)` e `dm/dφ`, dove `m=(θ SX+θ DX)/2`. Un valore 0.5 significa che localmente 1° dell’albero produce circa 0.5° di sterzata media; il segno indica il verso. Il CSV contiene anche i due angoli ruota e gli errori di chiusura dei collegamenti. La mappa è esportata soltanto sul tratto continuo e monotono collegato alla posa neutra. È quindi invertibile per quel montaggio, ma è un modello ideale da calibrare sul prototipo, non una misura del sistema reale.

### Soluzione e limiti del comando

Per un dato angolo medio, il nucleo risolve la chiusura dello sterzo e trova Q mediante intersezione esatta dei cerchi `(M, r)` e `(T, s)`. Questo determina φ(m) per il montaggio selezionato. Il problema diretto φ→m viene risolto per bisezione su un settore continuo e monotono, senza scegliere arbitrariamente fra soluzioni diverse. Il browser esegue lo stesso calcolo localmente a ogni fotogramma, senza richieste Python.

La sensibilità deriva dal vincolo `|T−Q|²=s²`:

```text
S = dm/dφ = [(T−Q) · J(Q−M)] / [(T−Q) · dT/dm]
```

La derivata di T rispetto all’angolo medio è analitica. La ricerca iniziale del settore usa 256 intervalli per lato e raffina i confini con 48 passi di bisezione. Si arresta al primo limite di chiusura, punto morto dell’attuatore, limite passivo dello sterzo o escursione di 180° dell’albero dalla posa neutra. Non presume rotazione completa del motore. Questa individuazione numerica del settore non è un’ottimizzazione né una prova simbolica di assenza di ogni possibile singolarità fra i campioni.

I grafici e il CSV sono campionati su 181 angoli motore e vengono preparati soltanto su richiesta. Le sensibilità non definite vicino a una singolarità sono omesse. La corsa passiva dello sterzo e quella disponibile con l’attuatore sono mostrate separatamente; la corsa motore può essere asimmetrica anche con staffe speculari.

Non sono calcolati forze, coppia, attrito, deformazioni, giochi, sospensioni o dinamica. Il JGA25-370 è indicato nella specifica come 12 V, circa 58 RPM, senza encoder integrato: non sono inventate dimensioni dell’albero o coppia disponibile. L’angolo rappresentato è quello dell’uscita del riduttore; un comando PWM non equivale a un angolo noto. Il controllo reale richiederà feedback o riferimenti e una calibrazione.

## Ottimizzazione motore e confronto Pareto

La scheda **Ottimizzazione motore** mantiene fissa la geometria dello sterzo al momento della ricerca e imposta l’attacco al centro del tirante (λ=0.5). Inserisci la sterzata media richiesta (per esempio ±25°), le lunghezze disponibili della leva e dell’astina, una zona rettangolare oppure una posizione fissa per l’asse M. Si provano esattamente le lunghezze elencate, non misure intermedie: i valori iniziali sono a passi di 10 mm, ma puoi inserire qualunque elenco reale di interassi fra fori.

La zona Y è espressa come distanza dietro al tirante nella posa neutra: `M_y = Y_tirante_zero + distanza`. Il vincolo minimo riguarda l’asse, non il bordo del corpo motore. Il corpo motore non viene verificato: il suo montaggio è affidato alla zona scelta. Le interferenze della leva e dell’astina sono invece filtrate lungo la corsa richiesta. Il passo della griglia limita le posizioni esplorate; l’estremo superiore di una zona è incluso solo se cade sulla griglia. Entrambi i montaggi A/B sono provati. Prima della ricerca completa, un prefiltro vettoriale verifica `|R − L| < D < R + L` a ruote dritte e sulle distanze minime/massime delle 241 pose richieste. Allineamenti ed assi fuori margine sono esclusi; il test è comune ad A/B. L’anteprima mostra combinazioni teoriche, scartate inizialmente, scartate lungo la corsa e montaggi rimasti da analizzare. Il limite di 10000 vale soltanto per questi ultimi, non per il prodotto cartesiano originale. Il prefiltro ha un limite separato di 2000000 combinazioni teoriche per evitare griglie eccessive. La griglia si può visualizzare anche quando le combinazioni teoriche superano 10000; solo oltre 10000 posizioni motore il disegno dei punti viene omesso.

Per ogni candidato sopravvissuto al prefiltro si verificano chiusura, segno della trasmissione, sensibilità e interferenze 2D su **241 pose nello stesso intervallo richiesto**, inclusi estremi e centro. Leva e astina del motore vengono confrontate con ruote, bracci e staffe mediante intersezione dei rettangoli orientati; anche il semplice contatto scarta il candidato. Il tirante è escluso dagli ostacoli, come il corpo motore e la ferramenta. I controlli usano le dimensioni di **Ingombri 2D**. È un filtro su pose campionate, non una certificazione continua fra i campioni o un controllo 3D; eventuali componenti non rappresentati non sono verificati. I candidati che superano questo filtro vengono verificati anche contro il settore continuo del modello motore: la richiesta deve stare strettamente al suo interno, senza punto morto agli estremi. Il settore rimane individuato con la procedura numerica descritta sopra, non con una certificazione simbolica. Una barra mostra avanzamento e numero di candidati ammissibili, con riepilogo dei motivi di esclusione.

Si minimizzano due obiettivi, calcolati sullo stesso intervallo:

```text
S = |dm/dφ|
Obiettivo X = max(S), in °sterzata/°albero
Obiettivo Y = (max(S) − min(S)) / media(S), mostrato in percentuale
```

La media è campionata uniformemente in angolo medio dello sterzo. La misura percentuale distingue uniformità relativa e sensibilità assoluta. Il segno del montaggio non viene penalizzato. Un candidato è sul fronte Pareto se nessun altro candidato ammissibile è almeno altrettanto buono in entrambi gli obiettivi e strettamente migliore in almeno uno. I candidati con valori identici non si dominano. È il fronte del campione discreto scelto, non un ottimo globale sullo spazio continuo.

Nel grafico, clicca un rombo Pareto o usa il selettore per vedere la configurazione. Selezione e confronto sono limitati alle sole soluzioni Pareto; le altre possono essere mostrate come contesto. Il colore rappresenta la corsa albero richiesta oppure il margine di sterzata disponibile oltre la richiesta. Il margine è misurato rispetto al limite del settore del collegamento motore, che può includere anche i limiti dello sterzo o dell’escursione dell’albero. Puoi confrontare fino a tre configurazioni: il candidato selezionato più due aggiuntivi. Si sovrappongono la curva motore→sterzata e la sensibilità rispetto alla medesima sterzata; quest’ultima è mostrata in valore assoluto per default.

L’anteprima animata è indipendente dalla simulazione manuale e resta nella corsa richiesta, verificata per le interferenze campionate. Il margine cinematico oltre la richiesta non garantisce assenza di interferenze fuori da questa corsa. I grafici di confronto riguardano soltanto la corsa richiesta. Sono disponibili la tabella delle configurazioni ammissibili, il CSV dei risultati e il CSV della curva selezionata.

Solo **Carica nel simulatore** sostituisce la configurazione manuale con quella completa del candidato, incluso l’attacco centrale. Cambiare selezione, confrontare curve e animare l’anteprima non applica nulla. Modificare gli ingombri rende i risultati precedenti non selezionabili fino a una nuova ricerca. I risultati restano associati alla geometria fotografata all’avvio; se in seguito cambi lo sterzo, un avviso chiarisce che la ricerca va rilanciata per usarne i nuovi parametri.
