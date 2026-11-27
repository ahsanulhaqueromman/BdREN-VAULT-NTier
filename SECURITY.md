# Security

## Reporting a problem

Please do **not** open a public GitHub issue for a security problem. Contact the BdREN VAULT maintainers
directly through the BdREN network operations team, with:

- what you found and where (page, API path or script)
- how to reproduce it
- the version (the commit shown by `git log -1`) you tested

You will get an answer as soon as possible, and a fix will be released through the normal update
(`git pull` + `sudo bash deploy/install.sh`).

## What is protected, and how

| Area | Protection |
|---|---|
| Transport | HTTPS through nginx; HSTS and secure cookies when served over HTTPS |
| Browser | Strict Content Security Policy (scripts from the site only), no-sniff, same-origin referrer, clickjacking protection, CSRF tokens on every form |
| Portal sign-in | Django password hashing, minimum 12 characters; 5 wrong passwords lock that address and username for 5 minutes; nginx rate limit on `/login`; fail2ban; idle sign-out (15 minutes by default) |
| Authorisation | Viewer / Operator / Administrator roles checked on every page and API call; RADIUS / AAA, user management and reusing saved device logins are administrator-only; an Operator who changes a device's address or SSH port must type its password again |
| Device passwords | Encrypted with Fernet; the key is `data/secret.key` on the server only; hidden in the portal until **Show** is pressed |
| RADIUS user passwords | Never stored in clear text: salted SHA-256 for PAP and the NT hash for MS-CHAPv2 (MikroTik). The NT hash is unsalted, so keep the radius database and its backups private; CHAP is not supported |
| RADIUS protocol | BlastRADIUS (CVE-2024-3596) protection applied by the installer; rejected login records kept for 24 hours |
| RADIUS secrets | Hidden until **Show** or **Copy**; revealing one is logged |
| Saved configurations | SHA-256 checksum per version; files owned by the `vault` service user |
| RADIUS service | UDP 1812 / 1813 open only to NAS clients; firewall changed by a root-owned script without arguments; to stop password guessing, limit SSH/Telnet on the devices to management addresses with an ACL |
| Audit | Every portal sign-in, every change and every device login is recorded with time, user and source address |
| Secrets in Git | `.env`, `data/` and `*.key` are git-ignored; the installer creates them on the server |
| Server | Runs as an unprivileged `vault` user; unattended security updates; device access is read-only |

Known limitations are listed in [README.md](README.md#security).

## Operator checklist

- [ ] Use a domain name with a real certificate (`deploy/maintenance/set-domain.sh`) instead of the self-signed one
- [ ] Give the backup account on each device permission to **view** the configuration only, never to change it
- [ ] Keep one local administrator account on every device in case RADIUS is unreachable
- [ ] Run `deploy/maintenance/backup_vault.sh` nightly and copy `/var/backups/vault-dr/` off the server
- [ ] Keep `data/secret.key` in a safe place outside the server; without it saved device passwords cannot be recovered
- [ ] Remove portal accounts of people who leave, and review the Authentication Audit regularly
- [ ] Update regularly: `git pull` then `sudo bash deploy/install.sh`
