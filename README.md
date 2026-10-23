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

### La liaison
Curiosa n'envoie que des **mots d'action** (par exemple `lumieres:rouge`). C'est toi qui décides, chez toi, ce qu'ils lancent : **Paramètres > Appareils et services > Curiosa > Configurer**.
- **Ajouter une liaison** : mot d'action puis scène ou script. Exemple : `lumieres:rouge` -> `scene.rouge`.
- **Voix** : choisis un haut-parleur, un service de voix, la langue et le volume (facultatifs). Les mots d'action qui commencent par `tts:` lisent le texte reçu.

Seules les scènes et scripts que tu as liés, et le haut-parleur choisi, sont utilisés. Aucune autre entité n'est jamais touchée.

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

### The links
Curiosa only sends **action words** (for example `lights:red`). You decide at home what they start: **Settings > Devices & services > Curiosa > Configure**.
- **Add a link**: action word, then scene or script. Example: `lights:red` -> `scene.red`.
- **Voice**: pick a speaker, a voice service, language and volume (optional). Action words starting with `tts:` read the received text aloud.

Only the scenes and scripts you linked, and the chosen speaker, are used. No other entity is ever touched.

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
