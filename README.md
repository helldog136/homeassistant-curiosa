# Curiosa pour Home Assistant

[Français](#francais) | [English](#english)

<a id="francais"></a>
## Français

### À quoi ça sert
Avec cette intégration, les récompenses en points de chaîne de ton stream Twitch (gérées par ton site Curiosa) peuvent changer la couleur de tes lumières ou lire un message sur un haut-parleur. C'est **Home Assistant qui va chercher** ce qui est en attente sur ton site : rien n'est ouvert chez toi.

### Installation (HACS, 4 étapes)
1. Dans HACS, ouvre le menu (trois points) puis **Dépôts personnalisés**.
2. Ajoute `https://github.com/helldog136/homeassistant-curiosa` avec le type **Intégration**.
3. Cherche **Curiosa** dans HACS, télécharge, puis redémarre Home Assistant.
4. **Paramètres > Appareils et services > Ajouter une intégration > Curiosa**.

### Association
Dans l'admin de Curiosa, appuie sur **Associer Home Assistant** : un code de 8 caractères s'affiche (valable 10 minutes). Dans Home Assistant, tape l'adresse de ton site (`https://mon-site.com`) et le code. Si l'association est coupée plus tard depuis l'admin, Home Assistant te demande un nouveau code.

### Le parcours, en 4 lignes
1. **Crée la récompense sur ton site** (dans le Bot Twitch > Récompenses).
2. **Elle apparaît ici par son nom** : Paramètres > Appareils et services > Curiosa > Configurer > « Relier mes actions à un script ».
3. **Choisis le script** (ou la scène) qu'elle lance chez toi.
4. **C'est prêt.** Rien d'autre à taper.

Chaque action est affichée avec son état : « reliée à script.aspirateur » ou « pas encore reliée ». Pour défaire une liaison, ouvre l'action et laisse le choix vide. Si une récompense est utilisée alors qu'aucun script n'est relié, Home Assistant ajoute une **réparation** (Paramètres > Réparations) : « Une récompense demande « Lancer l'aspirateur » mais aucun script n'est relié ». Appuie sur « Corriger », choisis le script, et elle disparaît. Il y a au plus une réparation par action.

- **Voix** : choisis un haut-parleur, un service de voix, la langue et le volume (facultatifs). L'action « Lire le message à voix haute » se règle ici, pas dans la liste.
- **Bouton « Visiter »** : sur la page de l'appareil Curiosa, il ouvre ton site.
- **Avancé** (mode avancé de Home Assistant, ou site qui n'envoie pas encore sa liste d'actions) : ajouter ou supprimer à la main un mot d'action (par exemple `lumieres:rouge` -> `scene.rouge`).

La liste des actions vient de ton site (50 noms au plus). Elle est gardée ici pour que l'écran marche après un redémarrage, et **elle n'est jamais renvoyée au site**. Seules les scènes et scripts que tu as liés, et le haut-parleur choisi, sont utilisés. Aucune autre entité n'est jamais touchée.

**Mise à jour depuis la 0.1.0** : automatique. Tes liaisons sont gardées telles quelles ; elles prennent le nom de ton site dès que celui-ci envoie sa liste d'actions, et restent visibles (« ancienne liaison ») si leur action n'y figure plus.

### Sécurité, en clair
- **Ce que Home Assistant envoie** : le code d'association (une fois), son jeton, et pour chaque action un accusé de réception avec un code court (`ok`, `unmapped`, `disabled`, `expired`, `error`). **Rien d'autre** : ni lumières, ni états, ni noms d'entités, ni liste, ni nom de la maison.
- **Ce que Home Assistant reçoit** : un mot d'action et, pour la voix, un texte. Le texte est nettoyé une seconde fois ici (300 caractères max, balisage, adresses web et caractères cachés retirés).
- **Interrupteur « Curiosa actif »** : coupé, rien n'est exécuté, même si Curiosa envoie. Les actions reçues sont refusées avec le code `disabled` et Home Assistant continue de se signaler toutes les 30 secondes.
- **Expiration** : une action trop vieille (60 s par défaut côté site, 5 s de tolérance) n'est pas jouée. Une même action n'est jamais jouée deux fois.
- **Connexion** : https obligatoire. Les adresses locales ne passent qu'avec le « mode test ». Le jeton n'apparaît ni dans les journaux ni dans les diagnostics.
- La **dernière action** ne garde que le mot d'action : jamais le pseudo ni le texte.
- Quand le site envoie une **action de test** (bouton de vérification dans Curiosa), elle est exécutée normalement et marquée « test » dans le capteur et les journaux.

Le volume du haut-parleur reste modifié après un message si tu as réglé un volume.

<a id="english"></a>
## English

### What it is for
This integration lets the channel point rewards of your Twitch stream (managed by your Curiosa site) change your light colors or read a message on a speaker. **Home Assistant fetches** what is waiting on your site: nothing is opened at your home.

### Installation (HACS, 4 steps)
1. In HACS, open the menu (three dots), then **Custom repositories**.
2. Add `https://github.com/helldog136/homeassistant-curiosa` with type **Integration**.
3. Search **Curiosa** in HACS, download it, then restart Home Assistant.
4. **Settings > Devices & services > Add integration > Curiosa**.

### Pairing
In the Curiosa admin, press **Link Home Assistant**: an 8-character code appears (valid 10 minutes). In Home Assistant, type your site address (`https://my-site.com`) and the code. If the link is cut later from the admin, Home Assistant asks for a new code.

### The path, in 4 lines
1. **Create the reward on your site** (in Twitch Bot > Rewards).
2. **It shows up here by its name**: Settings > Devices & services > Curiosa > Configure > "Link my actions to a script".
3. **Pick the script** (or scene) it starts at home.
4. **You are ready.** Nothing else to type.

Each action is shown with its state: "linked to script.vacuum" or "not linked yet". To undo a link, open the action and leave the choice empty. If a reward is used while no script is linked, Home Assistant adds a **repair** (Settings > Repairs): "A reward asks for "Start the vacuum" but no script is linked". Press "Fix", pick the script, and it goes away. There is at most one repair per action.

- **Voice**: pick a speaker, a voice service, language and volume (optional). The "Read the message aloud" action is set up here, not in the list.
- **"Visit" button**: on the Curiosa device page, it opens your site.
- **Advanced** (Home Assistant advanced mode, or a site that does not send its action list yet): add or remove an action word by hand (for example `lights:red` -> `scene.red`).

The action list comes from your site (50 names at most). It is kept here so the screen works after a restart, and **it is never sent back to the site**. Only the scenes and scripts you linked, and the chosen speaker, are used. No other entity is ever touched.

**Updating from 0.1.0**: automatic. Your links are kept as they are; they take the name from your site as soon as it sends its action list, and stay visible ("old link") if their action is no longer in it.

### Security in plain words
- **What Home Assistant sends**: the pairing code (once), its key, and for each action a receipt with a short code (`ok`, `unmapped`, `disabled`, `expired`, `error`). **Nothing else**: no lights, no states, no entity names, no lists, no house name.
- **What Home Assistant receives**: an action word and, for voice, a text. The text is cleaned a second time here (300 characters max, markup, web addresses and hidden characters removed).
- **"Curiosa active" switch**: when off, nothing is run, even if Curiosa sends. Received actions are refused with code `disabled`, and Home Assistant keeps checking in every 30 seconds.
- **Expiry**: an action that is too old (60 s by default on the site, 5 s tolerance) is not played. The same action is never played twice.
- **Connection**: https is required. Local addresses only work in "test mode". The key never appears in logs or diagnostics.
- The **last action** only keeps the action word: never the name or the text.
- When the site sends a **test action** (check button in Curiosa), it runs normally and is marked "test" in the sensor and the logs.

The speaker volume stays changed after a message if you set a volume.

## Development
`pip install -r requirements_test.txt`, then `ruff check .` and `pytest`.

## Licence / License
See [LICENSE](LICENSE) (Curiosa License 1.0).
