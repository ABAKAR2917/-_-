# Configuration email SMTP pour JobSearch

L'envoi email est optionnel.

Si les variables SMTP ne sont pas configurees, JobSearch garde seulement les notifications internes dans le site.
Si elles sont configurees, JobSearch envoie aussi un email au destinataire.

Variables a configurer dans PowerShell avant de lancer le serveur :

```powershell
$env:SMTP_HOST = "smtp.gmail.com"
$env:SMTP_PORT = "587"
$env:SMTP_USER = "votre_email@gmail.com"
$env:SMTP_PASSWORD = "mot_de_passe_application"
$env:SMTP_FROM = "JobSearch <votre_email@gmail.com>"
$env:SMTP_TLS = "1"

C:\Python314\python.exe run_mysql.py
```

Exemples :

- Gmail : utiliser un mot de passe d'application, pas le mot de passe normal.
- Yandex/Mail.ru : utiliser le serveur SMTP et le mot de passe d'application du compte.

Quand un utilisateur recoit un message dans le chat, il recoit :

- une notification interne dans JobSearch ;
- un email si SMTP est configure.
