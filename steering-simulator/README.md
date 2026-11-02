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
2. Le dimensioni iniziali sono un parallelogramma con interasse 180 mm, bracci 30 mm, entrambi rivolti al retro, e tirante 180 mm. A ±25° le due staffe ruotano dello stesso angolo; T percorre un arco.
3. Apri gli espansori nella barra laterale per cambiare staffe, posizione delle ruote, geometria. Gli offset ruota sono vettori indipendenti dalla direzione dei bracci.
4. Le staffe sono sempre simmetriche. I tre controlli della geometria sono **Interasse perni A**, **Lunghezza Braccio** e **Lunghezza Tirante**. L’inclinazione viene calcolata: 0° indica bracci rivolti al retro, angoli positivi verso l’esterno e negativi verso l’interno. Gli offset della ruota DX sono specchiati automaticamente.
5. Le ruote sono sempre dritte nella posa iniziale. L’inclinazione viene calcolata automaticamente: `β = asin((t − d)/(2L))`. Le tre misure devono essere positive e soddisfare `|t − d| < 2L`: l’uguaglianza è una posa iniziale allineata e viene rifiutata. La regolazione manuale ha passo 10 mm e segnala le quote non modulari, senza arrotondare le misure importate. L’orientamento dei bracci non modifica l’orientamento iniziale delle ruote.
6. Metti in pausa o rilascia lo slider per acquisire la posa. In **Analisi**, apri la sezione cinematica e premi **Calcola grafici e diagnostica**: una barra di avanzamento accompagna il calcolo dei sei grafici e della diagnostica cinematica. L'indicatore rappresenta la posa acquisita; i risultati restano fermi finché non richiedi una nuova analisi.
7. **Ricerca quadrilatero** confronta liste di interassi A, lunghezze braccio e lunghezze tirante, tutte multiple di 10 mm. L’inclinazione viene ricavata per ciascun candidato. Si scelgono corsa media richiesta e passo virtuale (200 mm iniziali); il Pareto confronta escursione massima, errore Ackermann massimo e movimento minimo di T per grado di sterzo. Nessuno viene applicato senza il relativo comando.
8. In alto trovi sempre **Apri**, **Salva** ed **Esporta report**. Il progetto JSON conserva configurazione, impostazioni delle ricerche, risultati, selezioni, confronti e grafici già calcolati. Il report HTML è autonomo e stampabile in PDF dal browser. I CSV restano disponibili nelle sezioni di analisi e negli espansori delle ricerche.

### Animazione fluida e analisi separate

Il movimento è disegnato su un canvas locale tramite `requestAnimationFrame`, sincronizzato con il refresh del browser (tipicamente 60 Hz, dipendente dal dispositivo). Il browser ricava gli angoli delle ruote dall’angolo medio richiesto e risolve la chiusura esatta a ogni fotogramma: **nessuna interpolazione che allunghi le aste**. Python invia i parametri e le frontiere analitiche del ramo solo quando cambia il progetto. Non ci sono chiamate a Python, aggiornamenti Streamlit o ricostruzioni Plotly durante l'animazione.

Avvia/Pausa, slider, velocità, zoom, spostamento della vista e opzioni grafiche funzionano direttamente nel browser. Pausa, reset e rilascio dello slider inviano una singola posa a Python per l'eventuale analisi. I grafici, il confronto fra candidati e il CSV si calcolano soltanto con i rispettivi pulsanti, con indicatore di caricamento. Cambiando parametri vengono invalidati i risultati precedenti e la simulazione riparte ferma dalla posa zero. I controlli dei punti morti e del ramo restano attivi durante il movimento; gli ingombri fisici si verificano nella diagnostica su richiesta.

Il piccolo nucleo JavaScript dell'animazione replica la chiusura esatta e viene confrontato con il nucleo Python nei test di parità, incluse geometrie asimmetriche e i due rami. Non richiede librerie esterne né download dal browser. Gli inviluppi e le traiettorie vengono preparati una volta per geometria, non ricalcolati a ogni fotogramma.

### Dimensioni reali e dimensioni illustrative

Il modello conserva le lunghezze cinematiche, gli offset delle ruote e le dimensioni dei pneumatici (inizialmente 60 × 18 mm). La basetta, gli spessori, le quote Z e la ferramenta non sono modellati: si definiscono nel CAD.

La scheda **Ingombri 2D** raccoglie diametro ruote, larghezza pneumatici, larghezza comune dei braccetti e **diametro d’ingombro comune dei giunti B/Q** (gli ultimi due inizialmente 10 mm). La larghezza vale per bracci, staffe, tirante, leva e astina del motore; gli estremi rettangolari sporgono oltre il centro dei fori di metà larghezza. Queste misure aggiornano sia il browser sia la vista statica e il filtro delle interferenze, senza cambiare la cinematica. Il giunto Q riserva un disco del diametro impostato, mostrato tratteggiato in verde nell’animazione. Questo disco deve restare libero da ruote, bracci, staffe e anche dal tirante; il contatto con la propria leva e astina è previsto e ammesso. Viti e perni ordinari, spessori, quote Z e corpo motore restano esclusi. Gli altri simboli dei giunti sono decorativi e restano dentro i braccetti.

`docs/specification.md` conserva la specifica originale storica, antecedente alle semplificazioni concordate.

## Modello matematico

Lunghezze in **mm**, angoli interni e JSON in **radianti**, visualizzazione ed export CAD/CSV in **gradi**. X positivo verso destra, Y positivo verso il retro, fronte −Y. La visualizzazione pone +Y verso il basso e mantiene rapporto X:Y=1:1, con limiti indipendenti dall'angolo attuale.

```text
A SX = (0, 0)                        A DX = (d, 0)
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

La scheda **Ricerca quadrilatero** esplora fino a 2000 combinazioni di interasse perni A, lunghezza comune dei bracci e tirante. Accetta solo multipli positivi di 10 mm. L’origine della griglia di montaggio è A SX, con A DX = (d, 0): anche interassi come 190 mm sono costruibili e il disegno mostra A SX = (0, 0), A DX = (190, 0). I giunti mobili non sono vincolati alla griglia del telaio.

Le geometrie impossibili o allineate a zero sono scartate subito; le altre devono superare la corsa media richiesta prima del primo punto morto. Il passo virtuale è modificabile e parte da **200 mm**. Per ciascun candidato si usa la carreggiata fra i centri delle ruote a zero (`d + offset_X_DX − offset_X_SX`), non l’interasse dei perni A. Il riferimento ideale al 100% soddisfa `cot(esterna) − cot(interna) = carreggiata / passo`. L’angolo interno ideale è calcolato con `atan2(passo·sin(esterna), passo·cos(esterna) − carreggiata·sin(esterna))`, evitando la singolarità a zero. La coordinata della ruota esterna è quella reale del candidato.

L’obiettivo è il massimo di `|interna_reale − interna_ideale|` su **241 pose comuni da zero alla sterzata media richiesta**, espresso in gradi. Per simmetria il verso opposto è equivalente. Il fronte Pareto minimizza questo errore, massimizza l’escursione media totale disponibile fino al primo punto morto o a 90° e massimizza il **movimento minimo di T per grado di sterzata media**. Quest’ultimo è `min ||dT/dm|| · π/180`, in mm/°, calcolato tramite derivata analitica su 481 pose fra −richiesta e +richiesta. Si usa l’attacco materiale T impostato con λ; un suo cambio richiede una nuova ricerca. Entrambi i versi sono controllati perché per un attacco fuori centro il movimento può essere asimmetrico. È un indicatore dello spostamento disponibile, non la sensibilità finale in °ruote/°motore.

Il grafico 3D è ruotabile: X = errore (minore), Y = escursione (maggiore), Z = movimento minimo (maggiore). La vista 2D mantiene X/Y; il movimento minimo si legge nel tooltip. In entrambe le viste i punti Pareto sono cerchi blu, le geometrie dominate sono grigie (se abilitate) e un contorno scuro identifica la selezionata. Non si usano scale colori. Un punto può essere Pareto grazie al terzo obiettivo anche se appare dominato nella proiezione 2D. Il fronte viene ricalcolato con dominanza su tutti e tre gli obiettivi, mantenendo le soluzioni equivalenti. La metrica dell’errore non include la corsa oltre quella richiesta e rimane una stima campionata del massimo.

Selezione e confronto riguardano soltanto i candidati Pareto, tramite menu o clic sui punti della vista 2D; le geometrie dominate possono essere mostrate come contesto. Le curve sovrappongono angolo interno reale/ideale rispetto all’angolo esterno e mostrano l’errore con segno lungo la sterzata media: positivo indica interna più sterzata dell’ideale, negativo meno sterzata. Una curva aggiuntiva mostra i mm/° di T lungo entrambi i versi della corsa. Un cambio dell’offset X delle ruote richiede una nuova ricerca perché cambia il riferimento di carreggiata. Il passo virtuale è un parametro dell’analisi: non modifica la geometria reale né il modello motore.

Si possono confrontare fino a tre geometrie e animare il solo quadrilatero senza motore. Soltanto **Carica quadrilatero nel simulatore** applica d, L, t e inclinazione derivata, conservando motore, offset ruote e ingombri correnti. La ricerca non usa il motore né verifica interferenze fisiche; la successiva ottimizzazione motore è separata. Le nuove sessioni partono da bracci di 30 mm, modulari; le misure dei progetti esistenti non vengono arrotondate automaticamente.

## Salvataggio, report e configurazioni

`configs/default.json` contiene la configurazione iniziale. Il formato è versionato (`schema_version: 8`) e include unità, geometria cinematica, dimensioni delle ruote, larghezza comune dei braccetti e diametro comune riservato ai giunti B/Q, geometria motore, intervallo visualizzato, λ, simmetria e ramo selezionato. Gli angoli nel JSON sono in radianti. Il JSON dichiara `coordinate_origin: "A_SX"`; la posizione motore è espressa da A SX come nell’interfaccia. Gli schemi 5, 6 e 7 (coordinate centrate) vengono ancora letti preservando la configurazione fisica. Per gli schemi 5 e 6, il nuovo diametro d’ingombro di Q assume 10 mm; in assenza della larghezza dei braccetti viene usato il precedente valore grafico di 10 mm, visibile e modificabile nella nuova scheda. I vecchi file degli schemi 1, 2, 3 e 4 sono rifiutati esplicitamente, senza conversioni automatiche o parametri nascosti. Il caricamento nell’app richiede staffe simmetriche, ruote dritte a zero, ramo neutro e interasse coerente con le tre regolazioni; configurazioni incompatibili vengono rifiutate senza modificarne silenziosamente le quote. Il caricamento controlla finitezza, intervalli e coerenza della simmetria; non esegue codice dal file. Il JSON di sola configurazione contiene le dimensioni; il progetto completo conserva anche la posa acquisita e i controlli della simulazione. Alla riapertura il movimento è sempre in pausa.

**Salva** permette di inserire nome e note e scaricare un progetto completo (`steering-lab-project`, versione 1). Metti in pausa l’animazione o rilascia lo slider prima di salvare per acquisire la posa. La voce secondaria **Solo configurazione geometrica** scarica il JSON leggero delle sole quote. **Apri** accetta entrambi i formati e sostituisce la sessione corrente.

Il progetto conserva separatamente ricerche quadrilatero e motore, relativi candidati e confronti, analisi già eseguite e grafici. Il caricamento non rilancia le ottimizzazioni. Se il modello di calcolo è cambiato, recupera configurazione e impostazioni e richiede di ricalcolare i risultati, avvisando esplicitamente. Il formato usa JSON e non esegue codice dal file.

**Esporta report** produce un HTML con geometria, quote, note, metriche e grafici disponibili, senza avviare nuove analisi. Apri il file anche senza connessione e usa **Stampa / Salva PDF**. Il report documenta le ipotesi del modello 2D e distingue le geometrie delle ricerche dalla configurazione corrente. Non contiene un modello CAD; il supporto meccanico resta da progettare nel proprio CAD.

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

Il collegamento è `M → Q → T`: M è il centro fisso dell’albero in uscita dal riduttore, M–Q la levetta, Q–T l’astina rigida snodata e T un punto materiale del tirante. I soli nuovi parametri sono posizione X/Y di M, lunghezza della leva, lunghezza dell’astina e montaggio A/B. L’attacco T si sceglie in millimetri lungo il tirante, dal centro del perno B SX. Internamente viene conservato come frazione λ = distanza / lunghezza del tirante, compatibile con i JSON esistenti. Questi parametri restano regolabili manualmente; la ricerca discreta si esegue soltanto nella pagina dedicata.

I valori iniziali (M = 30,25 mm; leva 15 mm; astina 60 mm; montaggio A) sono un esempio modificabile. Corsa e sensibilità sono ricalcolate sulle dimensioni attuali del quadrilatero. Non sono dimensioni validate per la fabbricazione.

La vista parte dal comando **Motore**: lo slider e la velocità si riferiscono all’albero, con 0° definito automaticamente nella posa con ruote dritte. **Sterzata libera** permette di osservare il solo sterzo; fuori dalla corsa continua dell’attuatore l’astina viene omessa con un avviso, senza deformarla per raggiungere una posa impossibile. Se il montaggio non chiude già al centro, il comando motore è disabilitato e viene spiegato il problema. Il montaggio A/B è mantenuto fisso durante il movimento.

La sezione **Motore e sensibilità** nella scheda **Analisi** calcola su richiesta due curve: `m(φ)` e `dm/dφ`, dove `m=(θ SX+θ DX)/2`. Un valore 0.5 significa che localmente 1° dell’albero produce circa 0.5° di sterzata media; il segno indica il verso. Il CSV contiene anche i due angoli ruota e gli errori di chiusura dei collegamenti. La mappa è esportata soltanto sul tratto continuo e monotono collegato alla posa neutra. È quindi invertibile per quel montaggio, ma è un modello ideale da calibrare sul prototipo, non una misura del sistema reale.

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

La scheda **Ottimizzazione motore** mantiene fissa la geometria dello sterzo al momento della ricerca e prova i fori T scelti sul tirante. Per default usa i fori a passo 10 mm più vicini al centro: con tirante 170 mm, 80 e 90 mm da B SX; con 180 mm, 90 mm. **Fori specifici** permette di inserire un elenco di distanze da B SX, multiple di 10 mm comprese tra 0 e la lunghezza del tirante. Il passo sul tirante è indipendente dalla griglia del telaio: la coordinata di T a ruote dritte può quindi non essere multipla di 10 mm. Inserisci la sterzata media richiesta (per esempio ±25°), le lunghezze disponibili della leva e dell’astina, una zona rettangolare oppure una posizione fissa per l’asse M. Si provano esattamente le lunghezze elencate, non misure intermedie: i valori iniziali sono a passi di 10 mm, ma puoi inserire qualunque elenco reale di interassi fra fori.

La zona Y è espressa come distanza dietro al tirante nella posa neutra: i suoi limiti sono `Y_tirante_zero + distanza`, ma i punti motore restano sulla **griglia telaio fissa 10 × 10 mm**, senza traslarla con il tirante. La griglia, la vista, i campi motore, i risultati, i tooltip e gli export hanno un’unica origine: **A SX = (0, 0)**, con A DX = (d, 0). Le posizioni motore generate sono quindi espresse direttamente in multipli di 10 mm su X e Y, anche con interasse 190 mm. Il passo di ricerca deve essere multiplo di 10 mm e salta nodi a partire dal primo nodo ammesso dentro la zona. La posizione fissa fuori griglia viene rifiutata, mai arrotondata dopo il calcolo. Le quote Y minime vengono arrotondate verso l’interno della zona ai nodi ammessi, conservando il margine richiesto. Il caricamento copia le coordinate del candidato senza modificarle. Il vincolo minimo riguarda l’asse, non il bordo del corpo motore. Il corpo motore non viene verificato: il suo montaggio è affidato alla zona scelta. Le interferenze della leva e dell’astina sono invece filtrate lungo la corsa richiesta. Il passo limita le posizioni esplorate; i bordi sono inclusi solo se cadono sui nodi campionati della griglia. Entrambi i montaggi A/B sono provati. Prima della ricerca completa, un prefiltro vettoriale verifica `|R − L| < D < R + L` a ruote dritte e sulle distanze minime/massime delle 241 pose richieste. Allineamenti ed assi fuori margine sono esclusi; il test è comune ad A/B. L’anteprima mostra combinazioni teoriche, scartate inizialmente, scartate lungo la corsa e montaggi rimasti da analizzare. Non c’è un limite di 10000 ai montaggi da analizzare: la ricerca percorre i candidati progressivamente, senza conservare l’elenco completo degli indici. Si mantengono soltanto le soluzioni che superano tutti i controlli e i conteggi dei motivi di esclusione. Il limite di memoria è **50000 soluzioni ammissibili**: trovare la 50001ª interrompe la ricerca con un errore esplicito, senza pubblicare un insieme parziale come risultato finale. Il prefiltro ha un limite separato di 2000000 combinazioni teoriche per evitare griglie eccessive. Il numero di tentativi non limita l’anteprima; solo oltre 10000 posizioni motore il disegno dei punti viene omesso.

Per ogni candidato sopravvissuto al prefiltro si verificano chiusura, segno della trasmissione, sensibilità e interferenze 2D su **241 pose nello stesso intervallo richiesto**, inclusi estremi e centro. Leva e astina del motore vengono confrontate con ruote, bracci e staffe mediante intersezione dei rettangoli orientati; anche il semplice contatto scarta il candidato. Per leva e astina il tirante resta escluso dagli ostacoli. Il disco d’ingombro di Q viene invece confrontato esattamente con tutti i rettangoli orientati, incluso il tirante, mediante distanza al rettangolo (anche agli spigoli). Corpo motore e altra ferramenta restano esclusi. I controlli usano le dimensioni di **Ingombri 2D**. È un filtro su pose campionate, non una certificazione continua fra i campioni o un controllo 3D; eventuali componenti non rappresentati non sono verificati. I candidati che superano questo filtro vengono verificati anche contro il settore continuo del modello motore: la richiesta deve stare strettamente al suo interno, senza punto morto agli estremi. Il settore rimane individuato con la procedura numerica descritta sopra, non con una certificazione simbolica. Una barra mostra avanzamento e numero di candidati ammissibili, con riepilogo dei motivi di esclusione.

Si minimizzano due obiettivi, calcolati sullo stesso intervallo:

```text
S = |dm/dφ|
Obiettivo X = max(S), in °sterzata/°albero
Obiettivo Y = (max(S) − min(S)) / media(S), mostrato in percentuale
```

La media è campionata uniformemente in angolo medio dello sterzo. La misura percentuale distingue uniformità relativa e sensibilità assoluta. Il segno del montaggio non viene penalizzato. Un candidato è sul fronte Pareto se nessun altro candidato ammissibile è almeno altrettanto buono in entrambi gli obiettivi e strettamente migliore in almeno uno. I candidati con valori identici non si dominano. È il fronte del campione discreto scelto, non un ottimo globale sullo spazio continuo.

Nel grafico, clicca un rombo Pareto o usa il selettore per vedere la configurazione. Selezione e confronto sono limitati alle sole soluzioni Pareto; le altre possono essere mostrate come contesto. Il Pareto usa punti blu per il fronte filtrato e grigio per quello originale, senza scala colori o regolazioni aggiuntive. Il margine è misurato rispetto al limite del settore del collegamento motore, che può includere anche i limiti dello sterzo o dell’escursione dell’albero. Puoi confrontare fino a tre configurazioni: il candidato selezionato più due aggiuntivi. Si sovrappongono la curva motore→sterzata e la sensibilità rispetto alla medesima sterzata; quest’ultima è mostrata in valore assoluto per default.

L’anteprima animata è indipendente dalla simulazione manuale e resta nella corsa richiesta, verificata per le interferenze campionate. Il margine cinematico oltre la richiesta non garantisce assenza di interferenze fuori da questa corsa. I grafici di confronto riguardano soltanto la corsa richiesta. Sono disponibili la tabella delle configurazioni ammissibili, il CSV dei risultati e il CSV della curva selezionata.

Solo **Carica nel simulatore** sostituisce la configurazione manuale con quella completa del candidato, incluso il foro T scelto. La sezione **Quote precise per il montaggio** riporta posizione M da A SX, foro T da B SX e B DX, coordinate di T/Q a ruote dritte e orientamento iniziale della leva. Le quote sono disponibili anche nel report e il CSV include il foro T e le sue coordinate iniziali. Il caricamento non trasla il motore: M rimane esattamente sul nodo telaio trovato. Cambiare selezione, confrontare curve e animare l’anteprima non applica nulla. Modificare gli ingombri rende i risultati precedenti non selezionabili fino a una nuova ricerca. I risultati restano associati alla geometria fotografata all’avvio; se in seguito cambi lo sterzo, un avviso chiarisce che la ricerca va rilanciata per usarne i nuovi parametri.

### Filtri sui risultati motore

**Filtra e confronta i risultati** restringe la ricerca già completata per lunghezze di leva/astina, zona X/Y del motore (da A SX) e montaggio A/B. Puoi svuotare un elenco per escludere tutti i suoi valori, oppure usare **Azzera filtri** per recuperare l’intero insieme. Tutte le soluzioni ammissibili originali restano in memoria: i filtri non eseguono una nuova ricerca e il Pareto viene ricalcolato sul sottoinsieme, promuovendo anche candidati precedentemente dominati. Il fronte originale resta grigio; contatori e differenze delle prestazioni indicano l’effetto delle scelte. Selezione e confronti riguardano soltanto il nuovo Pareto. Il CSV esporta il sottoinsieme filtrato; progetto e report conservano i filtri applicati.

Il filtro **Leva M–Q sempre dietro al tirante mobile** usa la posizione e l’inclinazione del tirante in ciascuna delle 241 pose della corsa richiesta. Il lato posteriore è la normale a B SX→B DX, orientata verso +Y nella posa neutra e solidale al tirante durante il movimento. Si proietta l’intero rettangolo della leva, comprese larghezza e sporgenze alle estremità, rispetto al bordo posteriore del tirante: il minimo spazio libero deve essere positivo; il contatto esclude il candidato. Il controllo si applica anche al prolungamento della linea del tirante, impedendo che la leva passi davanti aggirandone un’estremità. La distanza minima viene calcolata nella ricerca e memorizzata come un solo numero per candidato; il filtro può poi essere disattivato e riattivato senza ricalcolare la cinematica. È attivo inizialmente per le nuove ricerche. Le ricerche precedenti prive di questa misura richiedono un nuovo calcolo una sola volta. Resta una verifica 2D nelle pose campionate, non una certificazione continua tra i campioni.

### Consultare una soluzione motore

Dopo una ricerca, le impostazioni iniziali sono raccolte in un espansore chiuso. Il percorso principale è: filtri, scelta sul Pareto e soluzione selezionata. I filtri comprendono due intervalli X/Y del motore; il grafico mostra il fronte filtrato in blu e l’originale in grigio. Le tre metriche della soluzione e **Carica nel simulatore** restano accanto alla selezione.

Un solo selettore apre **Movimento** (vista iniziale), **Curve** o **Quote e CSV**. Solo la vista attiva viene preparata: il movimento usa due pose estreme per delimitare la corsa senza costruire le curve; le curve consentono fino a due confronti aggiuntivi e mostrano sempre la sensibilità in valore assoluto; quote, tabella completa e CSV vengono preparati quando richiesti. Scelta della vista e confronti vengono conservati nel progetto. Il report include i grafici della vista corrente.

### Filtri sui risultati del quadrilatero

La pagina **Ricerca quadrilatero** segue lo stesso percorso del motore: impostazioni della ricerca richiudibili, filtri, Pareto e soluzione selezionata. I tre elenchi **Interassi A inclusi**, **Bracci inclusi** e **Tiranti inclusi** escludono soltanto geometrie già disponibili: non vengono ricalcolate cinematica, errore Ackermann o traiettorie. Il Pareto viene ricostruito sui tre obiettivi originali e può promuovere soluzioni prima dominate. Il fronte originale resta grigio e quello filtrato è blu, sia in 3D sia nella proiezione 2D. I migliori valori e le differenze rispetto all’insieme originale mostrano l’effetto delle scelte; non identificano necessariamente un’unica geometria.

**Azzera filtri** ripristina tutte le geometrie originali. La selezione e gli eventuali confronti sono limitati al Pareto filtrato. Le viste **Movimento**, **Curve** e **Quote e CSV** preparano solo ciò che è richiesto: il movimento del solo quadrilatero è inizialmente visibile, le curve Ackermann e movimento di T si calcolano e si conservano in cache su richiesta, il CSV contiene le geometrie filtrate e i nuovi indicatori Pareto. Progetto e report conservano filtri e selezione; il report include i grafici della vista corrente. Restano invariati passo virtuale, intervallo di valutazione, punto T e offset ruota della ricerca: modificarli richiede una nuova ricerca.

Il Pareto del quadrilatero si apre inizialmente in **2D**, con **sterzata massima** su X e **movimento minimo di T per grado** su Y: in alto a destra è meglio. L’errore Ackermann è una misura secondaria nell’interfaccia, leggibile nel tooltip, nelle curve e nella vista 3D. Il calcolo del Pareto continua a usare tutti e tre gli obiettivi; cambiare la vista non cambia quali soluzioni sono non dominate.

### Scheda Ackermann per la presentazione

Nella soluzione del quadrilatero è disponibile la vista **Ackermann**, separata dalla ricerca e dal Pareto. Mostra il passo usato nell’ottimizzazione, un passo equivalente stimato e l’errore massimo rispetto a quest’ultimo. Il passo è la distanza tra gli assi, non la lunghezza totale del veicolo; il valore equivalente è un riferimento cinematico, non una misura reale né una garanzia di idoneità del progetto.

La stima sceglie un solo rapporto carreggiata/passo non negativo che minimizza il massimo errore angolare della ruota interna sull’intera corsa di confronto, campionata uniformemente in sterzata media. Non adatta un passo diverso per ogni angolo. I grafici confrontano la curva reale con il riferimento della ricerca e quello equivalente, e mostrano gli errori con segno rispetto ai due riferimenti. Si usa la stessa carreggiata neutra della ricerca; la simmetria rende equivalente il confronto nell’altro verso.

Ruote parallele corrispondono al limite di passo infinito; anche in caso anti-Ackermann il miglior riferimento positivo può essere questo limite, con errore residuo non nullo. I comportamenti misti sono indicati esplicitamente; angoli non rappresentabili nel normale riferimento positivo non producono un passo numerico fittizio. La scheda si calcola soltanto quando viene aperta e usa una cache; non cambia obiettivi, riferimento della ricerca o candidati. La scelta della vista e i grafici sono conservati nel progetto e inclusi nel report HTML quando questa è la vista corrente.

### Ingombro comune dei giunti B/Q

Il campo **Diametro ingombro giunti B/Q** nella scheda **Ingombri 2D** riserva lo stesso disco a B SX, B DX e Q. L’ottimizzazione motore controlla in tutte le pose campionate B contro leva M–Q e astina Q–T, e ciascun B contro Q mediante la somma dei raggi. Le verifiche comprendono anche il semplice contatto. Q continua a essere verificato contro ruote, bracci, staffe e tirante. I dischi B non vengono confrontati con il proprio braccio e tirante, ai quali sono collegati.

Se T coincide esattamente con B, il collegamento dell’astina a quel giunto è intenzionale. L’eccezione riguarda soltanto il proprio disco B e la sovrapposizione locale dei terminali; il resto del braccio, l’altro B, la leva e Q restano controllati. Il risultato espone i motivi di esclusione relativi a ciascun B. I cerchi tratteggiati sono visibili nel browser, nella configurazione fisica, nelle quote di montaggio e nel report. Il controllo è 2D e campionato, non una garanzia di montaggio tridimensionale.

Il valore viene salvato anche nei progetti. La chiave JSON storica `q_joint_diameter` è mantenuta per compatibilità e ora descrive l’ingombro comune B/Q: non è stato aggiunto un secondo diametro indipendente. Le ricerche precedenti devono essere ripetute per applicare i controlli sui giunti B; un avviso impedisce di presentarne i risultati come già verificati.

### Ingombro regolabile dell’asse motore

Nei filtri dei risultati motore, **Diametro ingombro asse M** definisce un disco fisso centrato su M (inizialmente Ø30 mm, 0 per disattivarlo). Il disco viene verificato nelle pose della corsa richiesta contro ruote, bracci, staffe, tirante, giunti B/Q e astina Q–T. La propria leva M–Q è esclusa perché connessa all’asse. Il cerchio è visibile nel movimento, nelle quote e nel report; lo spazio residuo minimo compare accanto alla soluzione e nel CSV.

I filtri fissi vengono applicati prima del controllo asse. Si verificano soltanto i candidati del fronte Pareto corrente; quando uno non passa viene escluso e si esamina il fronte che emerge. Le geometrie dominate da una soluzione già verificata non richiedono il calcolo. Il risultato è il Pareto esatto del campione che soddisfa il vincolo, senza dichiarare valide configurazioni dominate non verificate. Il numero di controlli dipende dalle esclusioni, non è limitato a 10–20. Un indicatore mostra quando vengono eseguite nuove verifiche.

Per ogni configurazione controllata si conserva un solo numero: il massimo raggio disponibile prima del contatto nella corsa campionata. Cambiare diametro riusa questo numero; nuove geometrie vengono verificate solo se diventano rilevanti sul Pareto. Riducendo il diametro o azzerando i filtri si possono recuperare le configurazioni originali, che restano in memoria. Il diametro e le distanze già calcolate vengono salvati nel progetto; non è necessario rilanciare l’ottimizzazione per modificarli. La verifica rimane 2D e limitata alle pose campionate.
