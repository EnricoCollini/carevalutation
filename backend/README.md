# API e motore di calcolo

Il server espone Flask su porta 5000. In produzione Gunicorn usa `app:create_app()`; il database si inizializza alla partenza con le tabelle `users` ed `evaluations`. Per una prima installazione questo è sufficiente; le future modifiche alla struttura del database richiederanno migrazioni esplicite.

## Database

Con Docker, definire `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER` e `MYSQL_PASSWORD`. Il server costruisce l'URL in modo sicuro anche se la password contiene caratteri speciali. `DATABASE_URL` ha priorità ed è utile nei test e nello sviluppo locale; `DB_URL` è accettato come alias. Senza variabili usa un file SQLite locale.

## Accesso

`POST /api/sessions` con `{ "nickname": "Luca", "password": "..." }` crea un profilo la prima volta e restituisce un `token` di sessione casuale. Per riaprire lo stesso nickname inviare nickname e password: se la password è corretta il server genera un nuovo `token`. La password è richiesta (minimo 6 caratteri) e nel database viene conservato soltanto il suo hash, mai in chiaro. Nickname o password errati restituiscono `401 invalid_credentials`. Un profilo creato prima dell'introduzione della password la imposta al primo accesso successivo.

Le rotte per le valutazioni richiedono `X-Session-Token`. Gli ID sono UUID e ogni query è filtrata anche per il proprietario.

## Rotte

| Rotta | Risultato |
|---|---|
| `GET /api/health` | Stato del server e database |
| `GET /api/catalog` | Marche/modelli indicativi e opzioni dei campi; il testo del modello resta libero |
| `POST /api/sessions` | Crea o riapre il profilo col nickname e codice |
| `GET /api/me` | Profilo attivo |
| `POST /api/calculate` | Calcola senza salvare, anche prima dell'accesso |
| `GET /api/evaluations` | Elenco delle valutazioni dell'utente |
| `POST /api/evaluations` | Calcola e salva; restituisce `{id,title,input,result,created_at,updated_at}` |
| `GET /api/evaluations/:id` | Legge una valutazione |
| `PUT /api/evaluations/:id` | Ricalcola e sostituisce una valutazione |
| `DELETE /api/evaluations/:id` | Elimina una valutazione |

Il corpo di `/api/calculate` e `/api/evaluations` contiene gli oggetti `vehicle`, `usage`, `insurance`, `tax`, `tyres`, `maintenance`, `revision`, `financing`, `budget` e `scenarios`. I campi vuoti possono produrre una valutazione provvisoria, ma `summary.missing_data` segnala cosa completare e `summary.affordability_label` diventa `dati_insufficienti`. Il prezzo d'acquisto positivo è obbligatorio.

`vehicle.residual_value` è facoltativo. Senza un valore inserito dall'utente, il motore stima un intervallo da prezzo attuale, età, km futuri e canale di vendita. `summary.residual_method` vale `stima_interna_illustrativa`: non è un prezzo live né una quotazione professionale. Una permuta iniziale in `vehicle.trade_in_value` riduce la cassa all'acquisto ma non lo stesso costo economico dell'auto nuova. `usage.electric_share` è una percentuale da 0 a 100.

Se si conosce `vehicle.new_list_price` (prezzo nuovo originario), per un usato o km zero con data d'immatricolazione e km attuali il risultato include `purchase_estimate` con intervallo e confronto rispetto al prezzo richiesto. Anche questa è una stima illustrativa; non cambia il costo calcolato dal prezzo effettivamente concordato.

Il risultato contiene `summary`, `breakdown`, `annual`, `cash_calendar`, `events`, `scenarios`, `comparisons`, `assumptions` e `warnings`. Il calendario comprende l'esborso iniziale, assicurazione, bollo, rate, eventuale saldo del prestito e vendita. Le riparazioni future sono mostrate come riserva prevista, perché non sono fatture già dovute.

## Verifica locale

Da questa cartella, dopo aver creato un ambiente Python e installato `requirements-dev.txt`, eseguire `python -m pytest -q`. I test coprono l'esempio numerico del protocollo, il credito, la permuta, la riconciliazione tra cassa e costo, l'auto ibrida plug-in, i dati incompleti e l'isolamento dei profili.
